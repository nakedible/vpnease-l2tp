"""Translate an (X)HTML document expressed as a string into plain ASCII string.

The translated form should be suitable for e.g. e-mail, log entries, etc.
Translation is done by using w3m, which is assumed to live in 'w3m_path'
or must be supplied by user.

Limitations:
  * No text effects are really used by w3m:
    * Links and headings are rendered as plain text
    * Bolds, strongs, preformatted etc have no special markers in ASCII
    * (For instance, headings are not underlined using '-' or '='.)

  * To make links useful in this rendering, the contents of an <a> tag
    should contain an URI, not some descriptive text.  For instance, use

       <a href="http://test.com/">http://test.com/</a>

    or:

       <a href="http://test.com/">Test.Com [http://test.com/]</a>
    
    instead of:

       <a href="http://test.com/">Test.Com</a>

"""
__docformat__ = 'epytext en'

import os

from codebay.common import runcommand

# This default is for debian and ubuntu
w3m_path = '/usr/bin/w3m'

def render_to_text(content, columns=76, ppc=8, ppl=8, strip_empty_lines=True, w3m=None):
    _w3m = w3m
    if _w3m is None:
        if os.path.exists(w3m_path):
            _w3m = w3m_path
    if _w3m is None:
        raise Exception('cannot find w3m and not supplied by user')

    rc, stdout, stderr = runcommand.run([_w3m, '-T', 'text/html', '-dump', '-cols', str(columns), '-ppc', str(ppc), '-ppl', str(ppl)], stdin=str(content), retval=runcommand.FAIL)

    if strip_empty_lines:
        res = stdout.split('\n')
        while len(res) > 0 and res[0] == '':
            del res[0]
        while len(res) > 0 and res[-1] == '':
            del res[-1]

        return '\n'.join(res) + '\n'
    else:
        return stdout


        
