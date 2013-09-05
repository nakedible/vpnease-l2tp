"""SMTP send helpers for product web."""

import textwrap
import cStringIO
import mimetools
import mimetypes
import MimeWriter

from twisted.mail import smtp
from twisted.internet import defer

from codebay.common import logger

_log = logger.get('l2tpproductweb.email')

STRING_SANITY = 1024
MAX_CONTENT_SIZE = 64*1024*1024
MAX_ATTACHMENT_SIZE = 4*1024*1024

# Python modules: mimetools, mimetypes, MimeWriter
# http://docs.python.org/lib/module-StringIO.html
# http://docs.python.org/lib/module-cStringIO.html

def _format_smtp_message(from_addr, to_addr, subject, content, attachments):
    #
    #  The central problem in formatting SMTP messages correctly is to support
    #  non-US-ASCII characters correctly.  The solution here simply mimics what
    #  Thunderbird (Icedove) does when sending a message containing both ISO 8859-1
    #  and full Unicode characters.
    #
    #  The solution for headers and content is unfortunately different.
    #
    #
    #  ESMTP:
    #    * http://www.ietf.org/rfc/rfc2821.txt
    #    * http://www.ietf.org/rfc/rfc2822.txt
    #
    #  MIME (cannot send other an US-ASCII with 2822 format):
    #    * http://en.wikipedia.org/wiki/MIME
    #    * http://en.wikipedia.org/wiki/Unicode_and_e-mail
    #    * http://www.ietf.org/rfc/rfc2045.txt
    #    * http://www.ietf.org/rfc/rfc2046.txt
    #    * http://www.ietf.org/rfc/rfc2048.txt
    #    * http://www.ietf.org/rfc/rfc2049.txt
    #    * http://www.ietf.org/rfc/rfc2183.txt
    
    # FIXME: some problems with mixed UTF vs. non-UTF characters in header.
    # escape all?
    def _hdrescape(x):
        res = ''
        for i in xrange(len(x)):
            c = x[i]
            ci = ord(c)
            if (ci in [0x0a, 0x0d]):
                # suppress in headers
                pass
            elif (ci >= 0x20 and ci <= 0x7e):
                res += c
            else:
                # See: http://en.wikipedia.org/wiki/MIME#Encoded-Word
                utf = c.encode('utf-8')
                res += '=?UTF-8?Q?'
                for j in xrange(len(utf)):
                    res += '=%02X' % ord(utf[j])
                res += '?='
        return res

    def _bodyescape(x):
        res = ''
        for i in xrange(len(x)):
            c = x[i]
            ci = ord(c)
            if (ci >= 0x20 and ci <= 0x7e) or (ci in [0x0a, 0x0d]):
                res += c
            else:
                utf = c.encode('utf-8')
                for j in xrange(len(utf)):
                    res += '=%02X' % ord(utf[j])
        return res

    # Check sanity
    #
    # No checks are done for attachments at the moment.  The attachments are I/O objects
    # so we don't know their size off hand.  However, below, when we're creating a MIME
    # message, we'll limit the attachment size.
    if (len(from_addr) > STRING_SANITY) or \
       (len(to_addr) > STRING_SANITY) or \
       (len(subject) > STRING_SANITY) or \
       (len(content) > MAX_CONTENT_SIZE):
        raise Exception('parameter sanity check failed')

    # Escape from and to addresses - XXX: no support for non-ascii email addresses right now
    from_addr = from_addr.encode('ascii')
    to_addr = to_addr.encode('ascii')

    # Start building MIME message into a string I/O object
    fp = cStringIO.StringIO()
    mw = MimeWriter.MimeWriter(fp)
    mw.addheader('From', _hdrescape(from_addr))
    mw.addheader('To', _hdrescape(to_addr))
    mw.addheader('Subject', _hdrescape(subject))
    mw.addheader('Date', smtp.rfc822date())
    mw.addheader('Message-ID', smtp.messageid())
    mw.addheader('MIME-Version', '1.0')

    # Add body and possibly attachments
    if len(attachments.keys()) == 0:
        # XXX: using 'plist' of startbody() results in multiline encoding, which I dislike
        mw.addheader('Content-Transfer-Encoding', 'quoted-printable')
        mw.addheader('Content-Disposition', 'inline')
        mw.flushheaders()
        f = mw.startbody('text/plain; charset=UTF-8')   # XXX: format=flowed?
        f.write(_bodyescape(content))
    else:
        mw.flushheaders()
        mw.startmultipartbody('mixed')

        f = mw.nextpart()
        f.addheader('Content-Disposition', 'inline')
        f.addheader('Content-Transfer-Encoding', 'quoted-printable')
        f.flushheaders()
        f2 = f.startbody('text/plain; charset=UTF-8')   # XXX: format=flowed?
        f2.write(_bodyescape(content))

        for i in attachments.keys():
            f = mw.nextpart()
            f.addheader('Content-Disposition', 'inline; filename=%s' % i)  # FIXME: filter / escape filenames
            f.addheader('Content-Transfer-Encoding', 'base64')
            f.flushheaders()

            mimetype, encoding = mimetypes.guess_type(i)
            f2 = f.startbody(mimetype)
            fdata = attachments[i]

            # We read the attachment into a variable here for base64 encoding (and
            # size check), this may take several megabytes of temporary memory.
            t = fdata.read(MAX_ATTACHMENT_SIZE + 1)
            if len(t) > MAX_ATTACHMENT_SIZE:
                raise Exception('attachment too long')
            f2.write(t.encode('base64'))

        mw.lastpart()
        
    # Done, convert to string and we're done
    return fp.getvalue()

def send_email(smtphost, smtpport, from_addr, to_addr, subject, contents, attachments={}):

    _header = ''
    
    _footer = textwrap.dedent("""\

    --
    www.vpnease.com
    """)
    
    wrapped_contents = _header + contents + _footer

    msg = _format_smtp_message(from_addr, to_addr, subject, wrapped_contents, attachments)
        
    def _log_result(res):
        _log.debug('sendmail result: %s' % repr(res))
        return res

    # Note: envelope 'from' is set to a bogus address because we don't want to generate
    # bounces to the sender email if something goes wrong!

    # should exist, otherwise bounces
    env_from = 'invalid@codebay.fi'
    env_to = [to_addr]
    d = smtp.sendmail(smtphost=smtphost,
                      from_addr=env_from,
                      to_addrs=env_to,
                      msg=msg,
                      senderDomainName=None,
                      port=smtpport)
    d.addCallbacks(_log_result, _log_result)
    
    # smtp.sendEmail is deprecated, but has some nice features, such as attachments.
    # We don't use it here, because even with the extra stuff, it still doesn't handle
    # non-US-ASCII characters correctly.

    return d

        
