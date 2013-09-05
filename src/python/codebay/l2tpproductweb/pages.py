
#
#  XXX:
#
#    - All page-to-page state must be maintained in hidden inputs or other client
#      side variables - this is the case because each request may go randomly to
#      any product web server due to DNS re-resolution.  See #783.
#
#    - Confirmation pages don't word wrap, resulting in potentially ugly outputs.
#
#
#  FIXME
#
#    - VAT validation in form directly; for every page with VAT
#
#    - Confirmation and e-mail contents check
#

import os
import gmpy
import textwrap
import formal

from twisted.internet import defer
from nevow import inevow, loaders, rend, tags as T
from formal import validation, iformal
from zope.interface import implements

from codebay.common import rdf
from codebay.common import rdftransact
from codebay.common import logger
from codebay.common import licensekey
from codebay.common import randutil
from codebay.nevow.formalutils import formalutils
from codebay.l2tpadmin import rdfdb
from codebay.l2tpadmin.rdfdefs import ns_l2tp_product_web as ns

from codebay.l2tpserver import constants
from codebay.l2tpproductweb import emailsend
from codebay.l2tpproductweb import invoicing
from codebay.l2tpproductweb import checkeuvatid

transact = rdftransact.transact
untransact = rdftransact.untransact
_log = logger.get('l2tpproductweb.pages')

# --------------------------------------------------------------------------
#
#  Constants
#

production_mode = True

SMTP_SERVER_ADDRESS = 'mail.vpnease.com'
SMTP_SERVER_PORT = 25
SUPPORT_EMAIL = 'support@vpnease.com'
SALES_EMAIL = 'sales@vpnease.com'
WEBPAGES_BASEDIR = '/var/local/vpnease-webpages'

if not production_mode:
    SMTP_SERVER_ADDRESS = '172.20.0.1'
    SMTP_SERVER_PORT = 25
    WEBPAGES_BASEDIR = '/home/sva/svn/l2tp-dev/src/python/productweb-pages/'

WRAP_LIMIT = 60

# --------------------------------------------------------------------------
#
#  Helpers
#

def word_wrap(text, width):
    if text is None:
        return None
    
    return reduce(lambda line, word, width=width: '%s%s%s' %
                  (line,
                   ' \n'[(len(line)-line.rfind('\n')-1
                          + len(word.split('\n',1)[0]
                                ) >= width)],
                   word),
                  text.split(' ')
                  )

# We need to remove CRs from any posted text areas.  Newlines in posted
# values are CR-LF, which causes problems if they are not cleaned up
# before using the values in e.g. e-mail.
def remove_crs(text):
    if text is None:
        return None    
    res = ''
    for i in text:
        if i == '\r':
            continue
        res += i
    return res

def get_filename(filename):
    res = os.path.join(WEBPAGES_BASEDIR, filename)
    return res

# These helpers are for encoding Unicode strings into e.g. query parameters
# for forwarding between pages.
def _query_encode(x):
    return x.encode('utf-8').encode('hex')

def _query_decode(x):
    return x.decode('hex').decode('utf-8')

# Consistent e-mail subject building
def _build_subject(subject_base, data, subjattr, default_subject='(no subject)'):
    subject = default_subject
    if data.has_key(subjattr) and data[subjattr] is not None:
        subject = data[subjattr]
    if subject == '':
        return '%s' % subject_base
    else:
        return '%s: %s' % (subject_base, subject)

class _SharedStuff:
    doc_content_file = 'doc-content.xhtml'

    def __init__(self):
        pass

    def macro_pagetitle(self, ctx):
        return self.get_page_title()

    def macro_legal_notice_uri(self, ctx):
        return constants.PRODUCT_WEB_SERVER_ADDRESS

    def macro_productname(self, ctx):
        return constants.PRODUCT_NAME

    def macro_right_box1(self, ctx):
        return loaders.xmlfile(get_filename(self.doc_content_file), pattern='right-box1')

    def macro_right_box2(self, ctx):
        return loaders.xmlfile(get_filename(self.doc_content_file), pattern='right-box2')

    def get_page_title(self):
        raise Exception('unimplemented')
    
    def get_menu_stan(self, current=None):
        m1 = T.li(_class='first')[T.a(href='index.html')['Home']]
        if current == 1:
            m1(_class='first current')
        m2 = T.li[T.a(href='product-home.html')['Product']]
        if current == 2:
            m2(_class='current')
        m3 = T.li[T.a(href='support-home.html')['Support']]
        if current == 3:
            m3(_class='current')
        m4 = T.li[T.a(href='partners-home.html')['Partners']]
        if current == 4:
            m4(_class='current')
        m5 = T.li[T.a(href='download-home.html')['Download']]
        if current == 5:
            m5(_class='current')
        m6 = T.li[T.a(href='http://www.vpnease.com/wiki/wiki')['Wiki']]
        if current == 6:
            m6(_class='current')
        return T.ul(_class='clear-float')[m1, m2, m3, m4, m5, m6]
        
    def get_side_nav_stan(self, nav_entries):
        res = T.invisible()
        for group in nav_entries:
            gtitle = group.pop(0)
            
            if gtitle is not None:
                res[T.h2[gtitle]]

            for ent in group:
                ul = T.ul()

                title = ent[0]
                link = ent[1]

                li = T.li()

                if title.startswith('*'):
                    title = title[1:]
                    ul(_class='form')
                    
                if len(ent) >= 3:
                    alternatives = ent[2]
                else:
                    alternatives = []
                if (self.uri == link) or (self.uri in alternatives):
                    li(_class='current')
                li[T.a(href=link)[title]]
                ul[li]
                res[ul]
            res[T.div(_class='group-end')]
        return res

    def get_where_heard_choice(self):
        # basic options, permute
        t = [
            ('news', 'News article'),
            ('search', 'Web search'),
            ('forums', 'Web forums'),
            ('friend', 'Friend or colleague'),
            ('salesperson', 'Sales person'),
            ]
        t = randutil.permute_list(t)
        
        # append 'other'
        t.append( ('other', 'Other (or don\'t care to comment)') )

        return formal.Field('whereheard', formal.String(required=True),
                            formal.widgetFactory(formal.RadioChoice, options=t),
                            label='How did you hear of VPNease? (*)')

    def get_in_eu_choice(self, field_id):
        t = [
            ('no', 'No'),
            ('yes', 'Yes'),
            ]

        return formal.Field(field_id, formal.String(required=True),
                            formal.widgetFactory(formal.RadioChoice, options=t),
                            label='Is your country a member of the European Union? (*)')
        
class _MoreInfoForm:
    askmore_email = None
    success_uri = None
    failure_uri = None
    
    def form_info(self, ctx):
        form = formal.Form()

        form.add(formal.Field('email', formal.String(required=True), label='Your e-mail address (*)'))
        form.add(formal.Field('subject', formal.String(required=False), label='Subject'))
        form.add(formal.Field('question', formal.String(required=True), formal.widgetFactory(formal.TextArea, cols=60, rows=8), label='Question (*)'))
        form.addAction(self.info_submitted, name='submit', label='Send', validate=True)

        return form

    def info_submitted(self, ctx, form, data):
        def _validation(res):
            pass

        def _submit(res):
            subject = _build_subject('Web request for more information', data, 'subject')

            # XXX: Unfortunately we don't get nice errors from all failures.  For instance,
            # if recipient mailbox does not exist, we'll get an apparent success since the
            # mail is "delivered" although it doesn't really go through.
            d = emailsend.send_email(SMTP_SERVER_ADDRESS, SMTP_SERVER_PORT, data['email'], self.askmore_email, subject, remove_crs(data['question']))
            d.addCallback(lambda x: None)
            return d

        def _success(res):
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling(self.success_uri)
            request.redirect(next_uri)
            return ''

        def _failure(reason):
            _log.error('ask more submit failed: %s' % reason)
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling(self.failure_uri)
            request.redirect(next_uri)
            return ''
            
        d = defer.Deferred()
        d.addCallback(_validation)
        d.addCallback(_submit)
        d.addCallbacks(_success, _failure)
        d.callback(None)
        return d

class LicenseKeyValidator(object):
    implements(iformal.IValidator)

    def __init__(self):
        pass

    def validate(self, field, value):
        try:
            # Required validation is someone else's problem
            if (value is None) or (value.strip() == ''):
                return
            
            lval, lbrk = licensekey.decode_license(value)
            if lval is None:
                raise Exception('Invalid key')
        except:
            raise validation.FieldValidationError, 'Invalid license key'

class EmailAddressValidator(object):
    implements(iformal.IValidator)

    def __init__(self):
        pass

    def validate(self, field, value):
        try:
            if (value is None) or (value == ''):
                return
            if len(value.split('@')) != 2:
                raise Exception('invalid')
            tmp = value.encode('ascii')  # must be ascii encodable (excepts here if not)
            # FIXME
            pass
        except:
            raise validation.FieldValidationError, 'Invalid e-mail address'

class BooleanValueValidator(object):
    implements(iformal.IValidator)

    def __init__(self, expect):
        self.expect = expect

    def validate(self, field, value):
        try:
            if (value is None):
                return

            # XXX: this could probably be done better
            if value != self.expect:
                raise Exception('Required')
        except:
            # XXX: not quite what we want to say in a "generic" boolean
            # validator.  However, this is shown in the web UI, so we
            # fake a useful string here now.
            raise validation.FieldValidationError, 'Required'

class EuVatIdValidator(object):
    implements(iformal.IValidator)

    def __init__(self):
        pass

    def validate(self, field, value):
        if (value is None):
            return

        # XXX: EU VAT ID validation using a SOAP request does not work because
        # Formal does not accept a deferred result from a validator (or rather,
        # it does, but ignores it because it is not an Exception).  So, this
        # validator can only do very primitive validation here, while more
        # comprehensive validation is done in the actual submit function which
        # does work with deferreds.
        #
        # See #784.
        
        try:
            value = value.strip().upper()
            if len(value) < 2:
                raise Exception('too short')
            # XXX

            #def _got_vat(res):
            #    if res:
            #        return
            #    else:
            #        raise validation.FieldValidationError, 'EU VAT ID on-line verification failed'
            #
            #vatid = value.strip().upper()
            #d = checkeuvatid.check_eu_vat_id(vatid)
            #d.addCallback(_got_vat)
            #return d
        except:
            raise validation.FieldValidationError, 'Invalid VAT ID'

# See #784.
def validate_eu_vat_id(fda, fieldname):
    vatid = fda[fieldname]
    if vatid is None:
        return defer.succeed(None)

    def _got_vat(res):
        if res:
            return
        else:
            fda.add_error(fieldname, 'EU VAT ID on-line verification failed')

    vatid = vatid.strip().upper()
    d = checkeuvatid.check_eu_vat_id(vatid)
    d.addCallback(_got_vat)
    return d

# --------------------------------------------------------------------------

class HomePage(rend.Page, _SharedStuff):
    docFactory = loaders.xmlfile(get_filename('home-template.xhtml'))
    contentfile = 'home-content.xhtml'
    
    def macro_menu(self, ctx):
        return self.get_menu_stan(1)

    def macro_bannertext(self, ctx):
        return loaders.xmlfile(get_filename(self.contentfile), pattern='bannertext')

    def macro_column1(self, ctx):
        return loaders.xmlfile(get_filename(self.contentfile), pattern='column1')

    def macro_column2(self, ctx):
        return loaders.xmlfile(get_filename(self.contentfile), pattern='column2')

    def macro_column3(self, ctx):
        return loaders.xmlfile(get_filename(self.contentfile), pattern='column3')

    def get_page_title(self):
        return 'Home'

# --------------------------------------------------------------------------

class ProductPage(rend.Page, _SharedStuff):
    docFactory = loaders.xmlfile(get_filename('doc-template.xhtml'))  # NB: intentional, shared
    contentfile = None
    uri = None
    
    def macro_menu(self, ctx):
        return self.get_menu_stan(2)
    
    def macro_nav(self, ctx):
        nav_entries = [ ['Product Information',
                         ['VPNease', 'product-home.html'],
                         ['Features', 'features.html'],
                         ['Product Comparison', 'product-comparison.html'],
                         ['Pricing', 'pricing.html'],
                         ['Payment Options', 'payment-options.html'],
                         ['*Buy License', 'buy-license.html', ['buy-license-confirm.html', 'buy-license-success.html', 'buy-license-failure.html']],
                         ['*Ask More', 'product-ask-more.html', ['product-ask-more-success.html', 'product-ask-more-failure.html']]],
                        
                        ['Legal Documents',
                         ['License Agreement', 'license-agreement.html'],
                         ['Privacy Policy', 'privacy-policy.html'],
                         ['Description of File', 'description-of-file.html'],
                         ['Dual Use', 'dual-use.html'],
                         ['Legal Notice', 'legal-notice.html']]
                        ]
        return self.get_side_nav_stan(nav_entries)
            
    def macro_content(self, ctx):
        return loaders.xmlfile(get_filename(self.contentfile), pattern='content')

    def get_page_title(self):
        return loaders.xmlfile(get_filename(self.contentfile), pattern='pagetitle')

class ProductHomePage(ProductPage):
    contentfile = 'product/product-home.xhtml'
    uri = 'product-home.html'

class FeaturesPage(ProductPage):
    contentfile = 'product/features.xhtml'
    uri = 'features.html'

class ProductComparisonPage(ProductPage):
    contentfile = 'product/product-comparison.xhtml'
    uri = 'product-comparison.html'

class PricingPage(ProductPage):
    contentfile = 'product/pricing.xhtml'
    uri = 'pricing.html'

class PaymentOptionsPage(ProductPage):
    contentfile = 'product/payment-options.xhtml'
    uri = 'payment-options.html'

class LicenseAgreementPage(ProductPage):
    contentfile = 'product/license-agreement.xhtml'
    uri = 'license-agreement.html'

class PrivacyPolicyPage(ProductPage):
    contentfile = 'product/privacy-policy.xhtml'
    uri = 'privacy-policy.html'

class DescriptionOfFilePage(ProductPage):
    contentfile = 'product/description-of-file.xhtml'
    uri = 'description-of-file.html'

class DualUsePage(ProductPage):
    contentfile = 'product/dual-use.xhtml'
    uri = 'dual-use.html'

class LegalNoticePage(ProductPage):
    contentfile = 'product/legal-notice.xhtml'
    uri = 'legal-notice.html'

class ProductAskMorePage(formal.ResourceMixin, ProductPage, _MoreInfoForm):
    contentfile = 'product/product-ask-more.xhtml'
    uri = 'product-ask-more.html'
    success_uri = 'product-ask-more-success.html'
    failure_uri = 'product-ask-more-failure.html'
    askmore_email = SALES_EMAIL
    
class ProductAskMoreSuccessPage(ProductPage):
    contentfile = 'product/product-ask-more-success.xhtml'
    uri = 'product-ask-more-success.html'

class ProductAskMoreFailurePage(ProductPage):
    contentfile = 'product/product-ask-more-failure.xhtml'
    uri = 'product-ask-more-failure.html'

class BuyLicensePage(formal.ResourceMixin, ProductPage):
    contentfile = 'product/buy-license.xhtml'
    uri = 'buy-license.html'
    
    def form_buy(self, ctx):
        form = formal.Form()

        form.add(formalutils.SubheadingField('subheading_legal', formal.String(required=False), label='Legal'))
        form.add(formal.Field('readlegal', formal.Boolean(required=True, validators=[BooleanValueValidator(True)]), label='I have read and accept VPNease End-User License Agreement, Privacy Policy, and other legal documents (*)'))

        form.add(formalutils.SubheadingField('subheading_contact', formal.String(required=False), label='Customer Information'))
        form.add(formal.Field('email', formal.String(required=True, validators=[EmailAddressValidator()]), label='Your e-mail address (*)'))
        form.add(formal.Field('name', formal.String(required=True), label='Company name (*)'))
        form.add(formal.Field('country', formal.String(required=True), label='Company country (*)'))
        form.add(formal.Field('business_id', formal.String(required=False), label='Business ID'))

        form.add(formalutils.SubheadingField('subheading_vat', formal.String(required=False), label='VAT Information'))
        form.add(self.get_in_eu_choice('in_eu'))
        euvatid_label = T.span()['EU VAT ID (if country within EU); see ', T.a(href='http://en.wikipedia.org/wiki/Value_added_tax_identification_number#European_Union_VAT_identification_numbers', target='_blank', _class='cb-external')['examples by country']]
        form.add(formal.Field('eu_vat_id', formal.String(required=False, validators=[EuVatIdValidator()]), label=euvatid_label))

        form.add(formalutils.SubheadingField('subheading_license', formal.String(required=False), label='License Information'))
        form.add(formal.Field('license_key', formal.String(required=False, validators=[LicenseKeyValidator()]), label='License key (if updating previous license)'))
        form.add(formal.Field('license_string', formal.String(required=False), label='License name (shown in product web UI, e.g. \'My Company Server #1\')'))
        form.add(formal.Field('license_user_connections', formal.Integer(required=True), label='Concurrent user count for license (see pricing) (*)'))
        form.add(formal.Field('license_sitetosite_connections', formal.Integer(required=True), label='Concurrent site-to-site connection count for license (see pricing) (*)'))

        form.add(formalutils.SubheadingField('subheading_additional', formal.String(required=False), label='Additional Information'))
        form.add(self.get_where_heard_choice())
        form.add(formal.Field('comments', formal.String(required=False), formal.widgetFactory(formal.TextArea, cols=60, rows=4), label='Comments'))

        # NB: validate is False because of EU VAT ID field on-line validation in buy_submitted()
        form.addAction(self.buy_submitted, name='submit', label='Next', validate=False)

        return form

    def buy_submitted(self, ctx, form, data):
        fda = formalutils.FormDataAccessor(form, [], ctx)

        temp = {}
        temp['vat_percent'] = 22
        temp['vat_status'] = 'Unknown'
        temp['vat_marking'] = 'Unknown'
        temp['contents'] = ''

        # XXX: this is actually now done twice, once here and once in the _vat_check below
        # Here we would like to check validity before stumbling on to a VAT check error.
        #
        # See #784.
        def _validation(res):
            # Do actual on-line EU VAT ID validation here because Formal does not support
            # deferreds in validator list.

            if data.has_key('eu_vat_id'):
                #d = validate_eu_vat_id(fda, 'eu_vat_id')

                # XXX: skip validation
                d = defer.succeed(None)
            else:
                d = defer.succeed(None)

            d.addCallback(lambda x: fda.finalize_validation())
            return d

        # See L2tpVatIssues for detailed discussion.
        def _vat_check(res):
            def _got_vat(res):
                temp['vat_percent'] = res.vat_percent
                temp['vat_status'] = res.vat_status
                temp['vat_marking'] = res.vat_marking
                return None

            country = None
            if data.has_key('country'):
                country = data['country']
            in_eu = False
            if data.has_key('in_eu') and data['in_eu'] == 'yes':
                in_eu = True
            business_id = None
            if data.has_key('business_id') and data['business_id'] is not None:
                business_id = data['business_id']
            eu_vat_id = None
            if data.has_key('eu_vat_id') and data['eu_vat_id'] is not None:
                eu_vat_id = data['eu_vat_id']

            d = invoicing.determine_vat(country, in_eu, business_id, eu_vat_id)
            d.addCallback(_got_vat)
            return d
        
        def _create_mail(res):
            # FIXME: floats, ugh, use gmpy
            temp['price_wo_vat'] = invoicing.compute_license_price_oct2007_float(data['license_user_connections'],
                                                                                 data['license_sitetosite_connections'])
            temp['price_vat'] = temp['price_wo_vat'] * (0.0 + temp['vat_percent'] / 100.0)
            temp['price_w_vat'] = temp['price_wo_vat'] * (1.0 + temp['vat_percent'] / 100.0)

            # Textual summary is probably now the best
            in_eu_str = ''
            if data['in_eu'] == 'yes':
                in_eu_str = 'Yes'
            else:
                in_eu_str = 'No'
            contents = textwrap.dedent(u"""\
            E-mail:                      %s
            Company name:                %s
            Company country:             %s
            Business ID:                 %s
            In EU:                       %s
            EU VAT ID:                   %s
            VAT status:                  %s

            License key:                 %s
            License name:                %s
            User count:                  %d
            Site-to-site count:          %d

            How did you hear of us?      %s

            Comments:
            %s

            --------------------------------------------------------------
            Monthly price (excl. VAT):   %8.2f EUR
            VAT (*):                     %8.2f EUR (%d %%)
            Customer EU VAT ID:          % 12s
            --------------------------------------------------------------
            Monthly TOTAL (incl. VAT):   %8.2f EUR
            (Please note: pricing is subject to change.)

            (*) %s
            """) % (data['email'],
                    data['name'] or '',
                    data['country'],
                    data['business_id'] or '',
                    in_eu_str,
                    data['eu_vat_id'] or '',
                    temp['vat_status'],
                    data['license_key'] or '',
                    data['license_string'] or '',
                    data['license_user_connections'],
                    data['license_sitetosite_connections'],
                    data['whereheard'] or '',
                    word_wrap(remove_crs(data['comments']), WRAP_LIMIT) or '(None)',
                    float(temp['price_wo_vat']),
                    float(temp['price_vat']),
                    temp['vat_percent'],
                    data['eu_vat_id'] or '',
                    float(temp['price_w_vat']),
                    temp['vat_marking'])

            temp['contents'] = contents
            
        def _success(res):
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling('buy-license-confirm.html')

            enc = _query_encode(temp['contents'])
            next_uri = next_uri.add('text_summary', enc)
            enc = _query_encode(data['email'])
            next_uri = next_uri.add('email', enc)
            request.redirect(next_uri)
            return ''

        def _failure(reason):
            _log.error('license purchase failed: %s' % reason)
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling('buy-license-failure.html')
            request.redirect(next_uri)
            return ''

        def _postvalidation(res):
            d = defer.Deferred()
            d.addCallback(_vat_check)
            d.addCallback(_create_mail)
            d.addCallbacks(_success, _failure)
            d.callback(None)
            return d

        # First deferred chain is for additional, deferred validation whose errback we
        # do *not* want to give (so we can signal form errors to Formal).  When that's
        # done, we setup the actual validation chain separately.
        #
        # XXX: catch non-Form-validation errors separately?
        
        d = defer.Deferred()
        d.addCallback(_validation)
        d.addCallback(_postvalidation)
        d.callback(None)
        return d

class BuyLicenseConfirmPage(formal.ResourceMixin, ProductPage):
    contentfile = 'product/buy-license-confirm.xhtml'
    uri = 'buy-license-confirm.html'

    def render_summary(self, ctx, data):
        ### from codebay.l2tpadmin import dbaccess

        def _render(res):
            request = inevow.IRequest(ctx)
            args = request.args
            if not args.has_key('__nevow_form__'):
                # first round
                return _query_decode(args['text_summary'][0])
            else:
                return ''

        d = defer.succeed(None)
        d.addCallback(_render)
        return d
    
    def form_buy(self, ctx):
        request = inevow.IRequest(ctx)
        form = formal.Form()
        form.add(formal.Field('text_summary', formal.String(required=True), formal.widgetFactory(formal.Hidden)))
        form.add(formal.Field('email', formal.String(required=True), formal.widgetFactory(formal.Hidden)))
        form.addAction(self.buy_submitted, name='submit', label='Confirm', validate=True)

        # This is really ugly but Formal is pretty nasty for chaining hidden variables.
        # On the first pass, request.args will be the variables from the previous page.
        # On submit of *this* page, request.args will be the values from the form actually
        # submitted, not needing a decode.
        #
        # This will now skip data filling on the second pass.
        #
        # FIXME: this is a pretty braindead approach, but we didn't find a better way
        # earlier in product development and I don't have a better idea now :-)
        
        # Another note: if we pass data with newlines (CR or LF) through hidden variables,
        # the browser will foul up and multiply the newlines!  So, we use hex encoded data
        # in hidden variables to prevent any mutilation.

        try:
            args = request.args
            _log.info('purchase license, args: %s' % repr(args))
            if not args.has_key('__nevow_form__'):
                # first round
                contents = args['text_summary'][0]
                email = args['email'][0]
                form.data['email'] = email
                form.data['text_summary'] = contents
        except:
            pass
        
        return form

    def buy_submitted(self, ctx, form, data):
        def _validation(res):
            pass
        
        def _send_email(res):
            _log.info('buy license, email data: %s' % data['text_summary'].encode('unicode_escape'))
            subject = _build_subject('VPNease license order confirmation', data, 'subject', '')
            email_addr = _query_decode(data['email'])
            contents = _query_decode(data['text_summary'])
            d = emailsend.send_email(SMTP_SERVER_ADDRESS, SMTP_SERVER_PORT, email_addr, SALES_EMAIL, subject, contents)
            return d

        def _success(res):
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling('buy-license-success.html')
            request.redirect(next_uri)
            return ''

        def _failure(reason):
            _log.error('buy license failed: %s' % reason)
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling('buy-license-failure.html')
            request.redirect(next_uri)
            return ''

        d = defer.Deferred()
        d.addCallback(_validation)
        d.addCallback(_send_email)
        d.addCallbacks(_success, _failure)
        d.callback(None)
        return d

class BuyLicenseSuccessPage(ProductPage):
    contentfile = 'product/buy-license-success.xhtml'
    uri = 'buy-license-success.html'

class BuyLicenseFailurePage(ProductPage):
    contentfile = 'product/buy-license-failure.xhtml'
    uri = 'buy-license-failure.html'

# --------------------------------------------------------------------------

class SupportPage(rend.Page, _SharedStuff):
    docFactory = loaders.xmlfile(get_filename('doc-template.xhtml'))
    contentfile = None
    uri = None
    
    def macro_menu(self, ctx):
        return self.get_menu_stan(3)
    
    def macro_nav(self, ctx):
        nav_entries = [ ['Support Information',
                         ['VPNease Support', 'support-home.html'],
                         ['Quick Installation Guide', 'quick-installation-guide.html'],
                         ['FAQ', 'faq.html'],
                         ['Test Servers', 'test-servers.html'],
                         ['*Support Request', 'support-request.html', ['support-request-success.html', 'support-request-failure.html']],
                         ['*Ask More', 'support-ask-more.html', ['support-ask-more-success.html', 'support-ask-more-failure.html']]],

                        ['Client Instructions',
                         ['Client Configuration', 'client-configuration.html']],

                        ['Server Installation',
                         ['Server Requirements', 'server-requirements.html'],
                         ['Server Installation', 'server-installation.html'],
                         ['Server BIOS Setup', 'server-bios-setup.html'], 
                         ['Virtualization Products', 'virtualization-products.html']],

                        ['Server Instructions',
                         ['Administration Interface', 'administration-interface.html'],
                         ['Site-to-site Configuration', 'site-to-site-configuration.html'],
                         ['Authentication Options', 'authentication-options.html'],
                         ['SNMP Monitoring', 'snmp-monitoring.html'],
                         ['Server Clustering', 'server-clustering.html'],
                         ['Multi-Customer Configuration', 'multi-customer-configuration.html']],

                        ['Technical Information',
                         ['Encryption and Standards', 'encryption-and-standards.html']]
                        ]

        return self.get_side_nav_stan(nav_entries)
            
    def macro_content(self, ctx):
        return loaders.xmlfile(get_filename(self.contentfile), pattern='content')

    def get_page_title(self):
        return loaders.xmlfile(get_filename(self.contentfile), pattern='pagetitle')

class SupportHomePage(SupportPage):
    contentfile = 'support/support-home.xhtml'
    uri = 'support-home.html'

class FaqPage(SupportPage):
    contentfile = 'support/faq.xhtml'
    uri = 'faq.html'
    
class TestServersPage(SupportPage):
    contentfile = 'support/test-servers.xhtml'
    uri = 'test-servers.html'
    
class QuickInstallationGuidePage(SupportPage):
    contentfile = 'support/quick-installation-guide.xhtml'
    uri = 'quick-installation-guide.html'

class ServerInstallationPage(SupportPage):
    contentfile = 'support/server-installation.xhtml'
    uri = 'server-installation.html'
    
class ServerBiosSetupPage(SupportPage):
    contentfile = 'support/server-bios-setup.xhtml'
    uri = 'server-bios-setup.html'
    
class ServerRequirementsPage(SupportPage):
    contentfile = 'support/server-requirements.xhtml'
    uri = 'server-requirements.html'
    
class VirtualizationProductsPage(SupportPage):
    contentfile = 'support/virtualization-products.xhtml'
    uri = 'virtualization-products.html'
    
class ClientConfigurationPage(SupportPage):
    contentfile = 'support/client-configuration.xhtml'
    uri = 'client-configuration.html'

class AdministrationInterfacePage(SupportPage):
    contentfile = 'support/administration-interface.xhtml'
    uri = 'administration-interface.html'

class SiteToSiteConfigurationPage(SupportPage):
    contentfile = 'support/site-to-site-configuration.xhtml'
    uri = 'site-to-site-configuration.html'

class EncryptionAndStandardsPage(SupportPage):
    contentfile = 'support/encryption-and-standards.xhtml'
    uri = 'encryption-and-standards.html'

class AuthenticationOptionsPage(SupportPage):
    contentfile = 'support/authentication-options.xhtml'
    uri = 'authentication-options.html'

class SnmpMonitoringPage(SupportPage):
    contentfile = 'support/snmp-monitoring.xhtml'
    uri = 'snmp-monitoring.html'
        
class ServerClusteringPage(SupportPage):
    contentfile = 'support/server-clustering.xhtml'
    uri = 'server-clustering.html'

class MultiCustomerConfigurationPage(SupportPage):
    contentfile = 'support/multi-customer-configuration.xhtml'
    uri = 'multi-customer-configuration.html'

class SupportAskMorePage(formal.ResourceMixin, SupportPage, _MoreInfoForm):
    contentfile = 'support/support-ask-more.xhtml'
    uri = 'support-ask-more.html'
    success_uri = 'support-ask-more-success.html'
    failure_uri = 'support-ask-more-failure.html'
    askmore_email = SUPPORT_EMAIL
    
class SupportAskMoreSuccessPage(SupportPage):
    contentfile = 'support/support-ask-more-success.xhtml'
    uri = 'support-ask-more-success.html'

class SupportAskMoreFailurePage(SupportPage):
    contentfile = 'support/support-ask-more-failure.xhtml'
    uri = 'support-ask-more-failure.html'
    
class SupportRequestPage(formal.ResourceMixin, SupportPage, _MoreInfoForm):
    contentfile = 'support/support-request.xhtml'
    uri = 'support-request.html'

    def form_support(self, ctx):
        form = formal.Form()

        # XXX: we would like to use a better widget with server-side file caching,
        # but DNS load balancing prevents this, see #783.

        form.add(formalutils.SubheadingField('subheading_information', formal.String(required=False), label='Request Information'))
        form.add(formal.Field('email', formal.String(required=True, validators=[EmailAddressValidator()]), label='Your e-mail address (*)'))
        form.add(formal.Field('license_key', formal.String(required=False, validators=[LicenseKeyValidator()]), label='License key (if applicable)'))
        form.add(formal.Field('subject', formal.String(required=False), label='Subject'))
        form.add(formal.Field('comments', formal.String(required=True), formal.widgetFactory(formal.TextArea, cols=60, rows=4), label='Comments (*)'))

        form.add(formalutils.SubheadingField('subheading_attachments', formal.String(required=False), label='Attachments (use ZIP if you have more attachments)'))
        form.add(formal.Field('attachment1', formal.File(required=False), label='Attachment 1'))
        form.add(formal.Field('attachment2', formal.File(required=False), label='Attachment 2'))
        form.add(formal.Field('attachment3', formal.File(required=False), label='Attachment 3'))
        form.addAction(self.support_submitted, name='submit', label='Send', validate=True)

        return form

    def support_submitted(self, ctx, form, data):
        def _validation(res):
            pass
        
        def _send_email(res):
            subject = _build_subject('Web support request', data, 'subject')
            contents = textwrap.dedent(u"""\
            E-mail:              %s
            License key:         %s
            Subject:             %s
            
            Comments:
            %s
            """) % (data['email'],
                    data['license_key'] or '',
                    data['subject'] or '',
                    word_wrap(remove_crs(data['comments']), WRAP_LIMIT) or 'None')

            attachments = {}
            for i in xrange(1, 4):
                attname = 'attachment%d' % i
                if data.has_key(attname) and data[attname] is not None:
                    fname, fcontents = data[attname]
                    if fname != '':
                        _log.debug('Attachment %s -> %s:%s' % (attname, fname, fcontents))
                        attachments[fname] = fcontents
                    
            d = emailsend.send_email(SMTP_SERVER_ADDRESS, SMTP_SERVER_PORT, data['email'], SUPPORT_EMAIL, subject, contents, attachments)
            return d

        def _success(res):
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling('support-request-success.html')
            request.redirect(next_uri)
            return ''
        
        def _failure(reason):
            _log.error('support request failed: %s' % reason)
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling('support-request-failure.html')
            request.redirect(next_uri)
            return ''
        
        d = defer.Deferred()
        d.addCallback(_validation)
        d.addCallback(_send_email)
        d.addCallbacks(_success, _failure)
        d.callback(None)
        return d

class SupportRequestSuccessPage(SupportPage):
    contentfile = 'support/support-request-success.xhtml'
    uri = 'support-request-success.html'

class SupportRequestFailurePage(SupportPage):
    contentfile = 'support/support-request-failure.xhtml'
    uri = 'support-request-failure.html'

# FIXME: mimetype automation

# --------------------------------------------------------------------------

class PartnersPage(rend.Page, _SharedStuff):
    docFactory = loaders.xmlfile(get_filename('doc-template.xhtml'))
    contentfile = None
    uri = None
    
    def macro_menu(self, ctx):
        return self.get_menu_stan(4)
    
    def macro_nav(self, ctx):
        nav_entries = [ ['Partner Information',
                         ['VPNease Partners', 'partners-home.html'],
                         ['Partner Benefits', 'partner-benefits.html'],
                         ['Partner Discounts', 'partner-discounts.html'],
                         ['*Request Partnership', 'request-partnership.html', ['request-partnership-success.html', 'request-partnership-failure.html']],
                         ['*Ask More', 'partner-ask-more.html', ['partner-ask-more-success.html', 'partner-ask-more-failure.html']]],

                        ['Service Providers',
                         ['Partner Process', 'service-provider-partner-process.html'],
                         ['Sales Materials', 'service-provider-partner-sales-materials.html'],
                         ['*Activate License', 'service-provider-partner-activate-license.html',
                          ['service-provider-partner-activate-license-confirm.html',
                           'service-provider-partner-activate-license-success.html',
                           'service-provider-partner-activate-license-failure.html']]],
                        
                        ['Installation Partners',
                         ['Partner Process', 'installation-partner-process.html'],
                         ['Sales Materials', 'installation-partner-sales-materials.html'],
                         ['*Activate License', 'installation-partner-activate-license.html',
                          ['installation-partner-activate-license-confirm.html',
                           'installation-partner-activate-license-success.html',
                           'installation-partner-activate-license-failure.html']]],

                        ['Legal Documents',
                         ['Partner License Agreement', 'partner-license-agreement.html']]
                        ]
        return self.get_side_nav_stan(nav_entries)
            
    def macro_content(self, ctx):
        return loaders.xmlfile(get_filename(self.contentfile), pattern='content')

    def get_page_title(self):
        return loaders.xmlfile(get_filename(self.contentfile), pattern='pagetitle')

class PartnersHomePage(PartnersPage):
    contentfile = 'partners/partners-home.xhtml'
    uri = 'partners-home.html'
    
class PartnerBenefitsPage(PartnersPage):
    contentfile = 'partners/partner-benefits.xhtml'
    uri = 'partner-benefits.html'
    
class PartnerDiscountsPage(PartnersPage):
    contentfile = 'partners/partner-discounts.xhtml'
    uri = 'partner-discounts.html'
    
class ServiceProviderPartnerProcessPage(PartnersPage):
    contentfile = 'partners/service-provider-partner-process.xhtml'
    uri = 'service-provider-partner-process.html'

class InstallationPartnerProcessPage(PartnersPage):
    contentfile = 'partners/installation-partner-process.xhtml'
    uri = 'installation-partner-process.html'

# XXX: same page for now
class ServiceProviderPartnerSalesMaterialsPage(PartnersPage):
    contentfile = 'partners/sales-materials.xhtml'
    uri = 'service-provider-partner-sales-materials.html'

# XXX: same page for now
class InstallationPartnerSalesMaterialsPage(PartnersPage):
    contentfile = 'partners/sales-materials.xhtml'
    uri = 'installation-partner-sales-materials.html'

class PartnerLicenseAgreementPage(PartnersPage):
    contentfile = 'partners/partner-license-agreement.xhtml'
    uri = 'partner-license-agreement.html'

class PartnerAskMorePage(formal.ResourceMixin, PartnersPage, _MoreInfoForm):
    contentfile = 'partners/partner-ask-more.xhtml'
    uri = 'partner-ask-more.html'
    success_uri = 'partner-ask-more-success.html'
    failure_uri = 'partner-ask-more-failure.html'
    askmore_email = SALES_EMAIL
    
class PartnerAskMoreSuccessPage(PartnersPage):
    contentfile = 'partners/partner-ask-more-success.xhtml'
    uri = 'partner-ask-more-success.html'

class PartnerAskMoreFailurePage(PartnersPage):
    contentfile = 'partners/partner-ask-more-failure.xhtml'
    uri = 'partner-ask-more-failure.html'

class RequestPartnershipPage(formal.ResourceMixin, PartnersPage):
    contentfile = 'partners/request-partnership.xhtml'
    uri = 'request-partnership.html'

    def form_partnership(self, ctx):
        form = formal.Form()

        form.add(formalutils.SubheadingField('subheading_legal', formal.String(required=False), label='Legal'))
        form.add(formal.Field('readlegal', formal.Boolean(required=True, validators=[BooleanValueValidator(True)]), label='I have read and accept VPNease Partner License Agreement, VPNease End-User License Agreement, Privacy Policy, and other legal documents (*)'))

        form.add(formalutils.SubheadingField('subheading_partner', formal.String(required=False), label='Requested Partnership'))
        form.add(formal.Field('partner_type', formal.String(required=True),
                              formal.widgetFactory(formal.RadioChoice, options=[ ('service-provider-partner', 'Service provider partner'),
                                                                                 ('installation-partner', 'Installation partner') ]),
                              label='Partner type (*)'))

        form.add(formalutils.SubheadingField('subheading_company', formal.String(required=False), label='Company Information'))
        form.add(formal.Field('company_name', formal.String(required=True), label='Company name (*)'))
        form.add(formal.Field('company_country', formal.String(required=True), label='Company country (*)'))
        form.add(formal.Field('company_business_id', formal.String(required=False), label='Company business ID'))
        form.add(formal.Field('company_email', formal.String(required=True, validators=[EmailAddressValidator()]), label='Company e-mail address (*)'))
        form.add(formal.Field('company_website', formal.String(required=False), label='Company web site'))
        form.add(formal.Field('company_phone', formal.String(required=False), label='Company phone number'))
        form.add(formal.Field('company_description', formal.String(required=True), formal.widgetFactory(formal.TextArea, cols=60, rows=4), label='Company description (*)'))

        form.add(formalutils.SubheadingField('subheading_vat', formal.String(required=False), label='Company VAT Information'))
        form.add(self.get_in_eu_choice('company_in_eu'))
        form.add(formal.Field('company_eu_vat_id', formal.String(required=False, validators=[EuVatIdValidator()]), label='Company EU VAT ID (if within EU)'))

        form.add(formalutils.SubheadingField('subheading_contact', formal.String(required=False), label='Contact Person'))
        form.add(formal.Field('contact_name', formal.String(required=True), label='Contact name (*)'))
        form.add(formal.Field('contact_email', formal.String(required=True, validators=[EmailAddressValidator()]), label='Contact e-mail address (*)'))
        form.add(formal.Field('contact_phone', formal.String(required=False), label='Contact phone number'))

        form.add(formalutils.SubheadingField('subheading_additional', formal.String(required=False), label='Additional Information'))
        form.add(self.get_where_heard_choice())
        form.add(formal.Field('comments', formal.String(required=False), formal.widgetFactory(formal.TextArea, cols=60, rows=4), label='Comments'))
        
        form.addAction(self.partnership_submitted, name='submit', label='Send', validate=False)

        return form

    def partnership_submitted(self, ctx, form, data):
        fda = formalutils.FormDataAccessor(form, [], ctx)

        def _validation(res):
            # Do actual on-line EU VAT ID validation here because Formal does not support
            # deferreds in validator list.

            if data.has_key('company_eu_vat_id'):
                #d = validate_eu_vat_id(fda, 'company_eu_vat_id')

                # XXX: skip validation
                d = defer.succeed(None)
            else:
                d = defer.succeed(None)

            d.addCallback(lambda x: fda.finalize_validation())
            return d
        
        def _send_email(res):
            subject = _build_subject('Web partnership request', data, 'subject', '')

            in_eu_str = 'No'
            if data.has_key('company_in_eu') and data['company_in_eu'] == 'yes':
                in_eu_str = 'Yes'

            contents = textwrap.dedent(u"""\
            Partner type:               %s

            Company name:               %s
            Company country:            %s
            Company business ID:        %s
            Company e-mail:             %s
            Company website:            %s
            Company phone:              %s
            Company within EU:          %s
            Company EU VAT ID:          %s

            Contact name:               %s
            Contact e-mail:             %s
            Contact phone:              %s

            How did you hear of us?     %s

            Company description:
            %s
            
            Comments:
            %s
            """) % (data['partner_type'],
                    data['company_name'],
                    data['company_country'] or '',
                    data['company_business_id'] or '',
                    data['company_email'],
                    data['company_website'] or '',
                    data['company_phone'] or '',
                    in_eu_str,
                    data['company_eu_vat_id'] or '',
                    data['contact_name'],
                    data['contact_email'],
                    data['contact_phone'] or '',
                    data['whereheard'] or '',
                    word_wrap(remove_crs(data['company_description']), WRAP_LIMIT) or '',
                    word_wrap(remove_crs(data['comments']), WRAP_LIMIT) or '')
            d = emailsend.send_email(SMTP_SERVER_ADDRESS, SMTP_SERVER_PORT, data['contact_email'], SALES_EMAIL, subject, contents)
            d.addCallback(lambda x: None)
            return d

        def _success(res):
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling('request-partnership-success.html')
            request.redirect(next_uri)
            return ''

        def _failure(res):
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling('request-partnership-failure.html')
            request.redirect(next_uri)
            return ''

        def _postvalidation(res):
            d = defer.Deferred()
            d.addCallback(_send_email)
            d.addCallbacks(_success, _failure)
            d.callback(None)
            return d

        d = defer.Deferred()
        d.addCallback(_validation)
        d.addCallback(_postvalidation)
        d.callback(None)
        return d

class RequestPartnershipSuccessPage(PartnersPage):
    contentfile = 'partners/request-partnership-success.xhtml'
    uri = 'request-partnership-success.html'

class RequestPartnershipFailurePage(PartnersPage):
    contentfile = 'partners/request-partnership-failure.xhtml'
    uri = 'request-partnership-failure.html'

class ServiceProviderPartnerActivateLicensePage(formal.ResourceMixin, PartnersPage):
    contentfile = 'partners/service-provider-partner-activate-license.xhtml'
    uri = 'service-provider-partner-activate-license.html'

    def form_activate(self, ctx):
        form = formal.Form()

        form.add(formal.Field('email', formal.String(required=True, validators=[EmailAddressValidator()]), label='Your e-mail address (*)'))
        form.add(formal.Field('license_key', formal.String(required=True, validators=[LicenseKeyValidator()]), label='License key (*)'))
        form.add(formal.Field('license_string', formal.String(required=False), label='License name (shown in product web UI, e.g. \'My Company Server #1\')'))
        form.add(formal.Field('license_user_connections', formal.Integer(required=True), label='Concurrent user count for license (*)'))
        form.add(formal.Field('license_sitetosite_connections', formal.Integer(required=True), label='Concurrent site-to-site connection for license (*)'))
        form.add(formal.Field('comments', formal.String(required=False), formal.widgetFactory(formal.TextArea, cols=60, rows=4)))
        form.addAction(self.activate_submitted, name='submit', label='Next', validate=True)

        return form

    def activate_submitted(self, ctx, form, data):
        temp = {}
        
        def _validation(res):
            pass

        def _create_mail(res):
            contents = textwrap.dedent(u"""\
            E-mail:              %s
            License key:         %s
            License string:      %s
            User count:          %d
            Site-to-site count:  %d
            
            Comments:
            %s
            """) % (data['email'],
                    data['license_key'],
                    data['license_string'],
                    data['license_user_connections'],
                    data['license_sitetosite_connections'],
                    word_wrap(remove_crs(data['comments']), WRAP_LIMIT) or '')
            temp['contents'] = contents

        def _success(res):
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling('service-provider-partner-activate-license-confirm.html')

            enc = _query_encode(temp['contents'])
            next_uri = next_uri.add('text_summary', enc)
            enc = _query_encode(data['email'])
            next_uri = next_uri.add('email', enc)
            request.redirect(next_uri)
            return ''

        def _failure(reason):
            _log.error('license activation failed: %s' % reason)
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling('service-provider-partner-activate-license-failure.html')
            request.redirect(next_uri)
            return ''

        d = defer.Deferred()
        d.addCallback(_validation)
        d.addCallback(_create_mail)
        d.addCallbacks(_success, _failure)
        d.callback(None)
        return d
    
class ServiceProviderPartnerActivateLicenseConfirmPage(formal.ResourceMixin, PartnersPage):
    contentfile = 'partners/service-provider-partner-activate-license-confirm.xhtml'
    uri = 'service-provider-partner-activate-license-confirm.html'

    def render_summary(self, ctx, data):
        request = inevow.IRequest(ctx)
        args = request.args
        if not args.has_key('__nevow_form__'):
            # first round
            return _query_decode(args['text_summary'][0])
        else:
            return ''

    def form_activate(self, ctx):
        request = inevow.IRequest(ctx)
        form = formal.Form()
        form.add(formal.Field('text_summary', formal.String(required=True), formal.widgetFactory(formal.Hidden)))
        form.add(formal.Field('email', formal.String(required=True), formal.widgetFactory(formal.Hidden)))
        form.addAction(self.activate_submitted, name='submit', label='Confirm', validate=True)

        try:
            args = request.args
            _log.info('license activation args: %s' % repr(args))
            if not args.has_key('__nevow_form__'):
                # first round
                contents = args['text_summary'][0]
                email = args['email'][0]
                form.data['email'] = email
                form.data['text_summary'] = contents
        except:
            pass

        return form

    def activate_submitted(self, ctx, form, data):
        def _validation(res):
            pass
        
        def _send_email(res):
            _log.info('license activation email data: %s' % data['text_summary'].encode('unicode_escape'))
            subject = _build_subject('Web license activation (service provider partner)', data, 'subject', '')
            email_addr = _query_decode(data['email'])
            contents = _query_decode(data['text_summary'])
            d = emailsend.send_email(SMTP_SERVER_ADDRESS, SMTP_SERVER_PORT, email_addr, SALES_EMAIL, subject, contents)
            d.addCallback(lambda x: None)
            return d

        def _success(res):
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling('service-provider-partner-activate-license-success.html')
            request.redirect(next_uri)
            return ''

        def _failure(reason):
            _log.error('license activation failed: %s' % reason)
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling('service-provider-partner-activate-license-failure.html')
            request.redirect(next_uri)
            return ''

        d = defer.Deferred()
        d.addCallback(_validation)
        d.addCallback(_send_email)
        d.addCallbacks(_success, _failure)
        d.callback(None)
        return d


class ServiceProviderPartnerActivateLicenseSuccessPage(PartnersPage):
    contentfile = 'partners/service-provider-partner-activate-license-success.xhtml'
    uri = 'service-provider-partner-activate-license-success.html'

class ServiceProviderPartnerActivateLicenseFailurePage(PartnersPage):
    contentfile = 'partners/service-provider-partner-activate-license-failure.xhtml'
    uri = 'service-provider-partner-activate-license-failure.html'

class InstallationPartnerActivateLicensePage(formal.ResourceMixin, PartnersPage):
    contentfile = 'partners/installation-partner-activate-license.xhtml'
    uri = 'installation-partner-activate-license.html'

    def form_activate(self, ctx):
        form = formal.Form()

        form.add(formalutils.SubheadingField('subheading_contact', formal.String(required=False), label='Customer Information'))
        form.add(formal.Field('email', formal.String(required=True, validators=[EmailAddressValidator()]), label='Customer e-mail address (*)'))
        form.add(formal.Field('name', formal.String(required=True), label='Customer company name (*)'))
        form.add(formal.Field('country', formal.String(required=True), label='Customer country (*)'))
        form.add(formal.Field('business_id', formal.String(required=False), label='Customer business ID'))

        form.add(formalutils.SubheadingField('subheading_vat', formal.String(required=False), label='Customer VAT Information'))
        form.add(self.get_in_eu_choice('in_eu'))
        form.add(formal.Field('eu_vat_id', formal.String(required=False, validators=[EuVatIdValidator()]), label='Customer EU VAT ID (if country within EU)'))

        form.add(formalutils.SubheadingField('subheading_license', formal.String(required=False), label='License Information'))
        form.add(formal.Field('license_key', formal.String(required=True, validators=[LicenseKeyValidator()]), label='License key (*)'))
        form.add(formal.Field('license_string', formal.String(required=False), label='License name (shown in product web UI, e.g. \'My Company Server #1\')'))
        form.add(formal.Field('license_user_connections', formal.Integer(required=True), label='Concurrent user count for license (*)'))
        form.add(formal.Field('license_sitetosite_connections', formal.Integer(required=True), label='Concurrent site-to-site connection for license (*)'))

        form.add(formalutils.SubheadingField('subheading_additional', formal.String(required=False), label='Additional Information'))
        form.add(formal.Field('cc_email', formal.String(required=False, validators=[EmailAddressValidator()]), label='Send a copy of activation confirmation to this e-mail address'))
        form.add(formal.Field('comments', formal.String(required=False), formal.widgetFactory(formal.TextArea, cols=60, rows=4)))
        form.addAction(self.activate_submitted, name='submit', label='Next', validate=False)

        return form

    def activate_submitted(self, ctx, form, data):
        fda = formalutils.FormDataAccessor(form, [], ctx)
        temp = {}
        
        def _validation(res):
            # Do actual on-line EU VAT ID validation here because Formal does not support
            # deferreds in validator list.

            if data.has_key('eu_vat_id'):
                #d = validate_eu_vat_id(fda, 'eu_vat_id')

                # XXX: skip validation
                d = defer.succeed(None)
            else:
                d = defer.succeed(None)

            d.addCallback(lambda x: fda.finalize_validation())
            return d

        def _create_mail(res):
            in_eu_str = ''
            if data['in_eu'] == 'yes':
                in_eu_str = 'Yes'
            else:
                in_eu_str = 'No'
            contents = textwrap.dedent(u"""\
            Customer e-mail:        %s
            Customer name:          %s
            Customer country:       %s
            Customer business ID:   %s
            Customer in EU:         %s
            Customer EU VAT ID:     %s
            
            License key:            %s
            License string:         %s
            User count:             %d
            Site-to-site count:     %d
            
            Comments:
            %s
            """) % (data['email'],
                    data['name'] or '',
                    data['country'] or '',
                    data['business_id'] or '',
                    in_eu_str,
                    data['eu_vat_id'] or '',
                    data['license_key'],
                    data['license_string'],
                    data['license_user_connections'],
                    data['license_sitetosite_connections'],
                    word_wrap(remove_crs(data['comments']), WRAP_LIMIT) or '')
            temp['contents'] = contents

        def _success(res):
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling('installation-partner-activate-license-confirm.html')

            enc = _query_encode(temp['contents'])
            next_uri = next_uri.add('text_summary', enc)
            enc = _query_encode(data['email'])
            next_uri = next_uri.add('email', enc)
            enc = _query_encode(data['cc_email'] or '')
            next_uri = next_uri.add('cc_email', enc)
            request.redirect(next_uri)
            return ''

        def _failure(reason):
            _log.info('license activation failed: %s' % reason)
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling('installation-partner-activate-license-failure.html')
            request.redirect(next_uri)
            return ''

        def _postvalidation(res):
            d = defer.Deferred()
            d.addCallback(_create_mail)
            d.addCallbacks(_success, _failure)
            d.callback(None)
            return d

        d = defer.Deferred()
        d.addCallback(_validation)
        d.addCallback(_postvalidation)
        d.callback(None)
        return d

class InstallationPartnerActivateLicenseConfirmPage(formal.ResourceMixin, PartnersPage):
    contentfile = 'partners/installation-partner-activate-license-confirm.xhtml'
    uri = 'installation-partner-activate-license-confirm.html'

    def render_summary(self, ctx, data):
        request = inevow.IRequest(ctx)
        args = request.args
        if not args.has_key('__nevow_form__'):
            # first round
            return _query_decode(args['text_summary'][0])
        else:
            return ''

    def form_activate(self, ctx):
        request = inevow.IRequest(ctx)
        form = formal.Form()
        form.add(formal.Field('text_summary', formal.String(required=True), formal.widgetFactory(formal.Hidden)))
        form.add(formal.Field('email', formal.String(required=True), formal.widgetFactory(formal.Hidden)))
        form.add(formal.Field('cc_email', formal.String(required=True), formal.widgetFactory(formal.Hidden)))
        form.addAction(self.activate_submitted, name='submit', label='Confirm', validate=True)

        try:
            args = request.args
            _log.info('license activation args: %s' % repr(args))
            if not args.has_key('__nevow_form__'):
                # first round
                contents = args['text_summary'][0]
                email = args['email'][0]
                cc_email = args['cc_email'][0]
                form.data['email'] = email
                form.data['text_summary'] = contents
                form.data['cc_email'] = cc_email
        except:
            pass

        return form

    def activate_submitted(self, ctx, form, data):
        def _validation(res):
            pass
        
        def _send_email(res):
            _log.info('license activation email data: %s' % data['text_summary'].encode('unicode_escape'))

            subject = _build_subject('Web license activation (installation partner)', data, 'subject', '')
            email_addr = _query_decode(data['email'])
            contents = _query_decode(data['text_summary'])
            d = emailsend.send_email(SMTP_SERVER_ADDRESS, SMTP_SERVER_PORT, email_addr, SALES_EMAIL, subject, contents)
            d.addCallback(lambda x: None)
            return d

        def _send_cc_email(res):
            if data.has_key('cc_email') and (data['cc_email'] is not None) and (data['cc_email'] != ''):
                _log.info('license activation CC email data: %s' % data['text_summary'].encode('unicode_escape'))

                subject = _build_subject('Web license activation (installation partner) (CC)', data, 'subject', '')
                email_addr = _query_decode(data['email'])
                cc_email_addr = _query_decode(data['cc_email'])
                contents = _query_decode(data['text_summary'])
                d = emailsend.send_email(SMTP_SERVER_ADDRESS, SMTP_SERVER_PORT, email_addr, cc_email_addr, subject, contents)
                d.addCallback(lambda x: None)
                return d
            else:
                return defer.succeed(None)
                
        def _success(res):
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling('installation-partner-activate-license-success.html')
            request.redirect(next_uri)
            return ''

        def _failure(reason):
            _log.error('license activation failed: %s' % reason)
            request = inevow.IRequest(ctx)
            next_uri = request.URLPath().sibling('installation-partner-activate-license-failure.html')
            request.redirect(next_uri)
            return ''

        d = defer.Deferred()
        d.addCallback(_validation)
        d.addCallback(_send_email)
        d.addCallback(_send_cc_email)
        d.addCallbacks(_success, _failure)
        d.callback(None)
        return d


class InstallationPartnerActivateLicenseSuccessPage(PartnersPage):
    contentfile = 'partners/installation-partner-activate-license-success.xhtml'
    uri = 'installation-partner-activate-license-success.html'

class InstallationPartnerActivateLicenseFailurePage(PartnersPage):
    contentfile = 'partners/installation-partner-activate-license-failure.xhtml'
    uri = 'installation-partner-activate-license-failure.html'

# --------------------------------------------------------------------------

class DownloadPage(rend.Page, _SharedStuff):
    docFactory = loaders.xmlfile(get_filename('doc-template.xhtml'))  # NB: intentional, shared
    contentfile = None
    uri = None
    
    def macro_menu(self, ctx):
        return self.get_menu_stan(5)
    
    def macro_nav(self, ctx):
        nav_entries = [ ['Downloads',
                         ['VPNease Download', 'download-home.html'],
                         ['Latest Version', 'latest-version.html'],
                         ['Previous Versions', 'previous-versions.html'],
                         ['Open Source', 'open-source.html' ]]
                        ]
        return self.get_side_nav_stan(nav_entries)
            
    def macro_content(self, ctx):
        return loaders.xmlfile(get_filename(self.contentfile), pattern='content')

    def get_page_title(self):
        return loaders.xmlfile(get_filename(self.contentfile), pattern='pagetitle')

class DownloadHomePage(DownloadPage):
    contentfile = 'download/download-home.xhtml'
    uri = 'download-home.html'

class LatestVersionPage(DownloadPage):
    contentfile = 'download/latest-version.xhtml'
    uri = 'latest-version.html'

class PreviousVersionsPage(DownloadPage):
    contentfile = 'download/previous-versions.xhtml'
    uri = 'previous-versions.html'

class OpenSourcePage(DownloadPage):
    contentfile = 'download/open-source.xhtml'
    uri = 'open-source.html'


# --------------------------------------------------------------------------

# FIXME - login, session, etc.
class PartnerSitePage(rend.Page, _SharedStuff):
    docFactory = loaders.xmlfile(get_filename('partner-template.xhtml'))
    contentfile = None
    uri = None
    
    def get_menu_stan(self, current=None):
        #m1 = T.li(_class='first')[T.a(href='index.html')['Partner Site']]
        #if current == 1:
        #    m1(_class='first current')
        #return T.ul(_class='clear-float')[m1]
        return ''

    def macro_menu(self, ctx):
        return self.get_menu_stan(1)

    def macro_nav(self, ctx):
        nav_entries = [ ['Product Licenses',
                         ['Product Licenses', 'licenses.html'],
                         ['Floating Licenses', 'floating-licenses.html'],
                         ['Fixme 3', 'fixme1.html'],
                         ['Fixme 4', 'fixme1.html'],
                         ['Fixme 5', 'fixme1.html'] ],
                        ]
        return self.get_side_nav_stan(nav_entries)
            
    def macro_content(self, ctx):
        return loaders.xmlfile(get_filename(self.contentfile), pattern='content')

    def get_page_title(self):
        return loaders.xmlfile(get_filename(self.contentfile), pattern='pagetitle')

    def get_username(self):
        # FIXME
        return 'test1'

    # FIXME
    def get_vat_percentage(self):
        return gmpy.mpq(22)
    
    # FIXME
    def is_service_provider(self):
        return True

    # FIXME
    def _format_gmpy_price(self, x, eurosign=True):
        t = x * gmpy.mpq(100)   # 123.4567 -> 12345.67
        t = int(gmpy.digits(t)) # 12345
        full = t / 100
        part = t % 100
        esign = ''
        if eurosign:
            esign = u' \u20ac'
        csep = '.'
        if full == 0:
            return u'0%s%02d%s' % (part, csep, esign)
        else:
            return u'%d%s%02d%s' % (full, csep, part, esign)

    def render_username(self, ctx, data):
        return self.get_username()
    
    def render_accounts(self, ctx, data):
        try:
            res = T.invisible()
            db = rdfdb.get_db()
            for i in rdfdb.get_accounts_sorted(db):
                res[T.p()[i.getS(ns.username, rdf.String)]]
            return res
        except:
            _log.exception('render_accounts failed')
            raise
        
    def _render_license(self, lic):
        res = T.div(_class='license')
        lic_state = ''
        if lic.getS(ns.licenseEnabled, rdf.Boolean, default=False):
            lic_state = 'Enabled'
        else:
            lic_state = 'Disabled'

        lic_price = int(invoicing.compute_license_price_oct2007(
            lic.getS(ns.licenseUserCount, rdf.Integer),
            lic.getS(ns.licenseSiteToSiteCount, rdf.Integer)
                ))
        if lic.getS(ns.licenseEnabled, rdf.Boolean, default=False):
            lic_price = u'%s \u20ac' % lic_price
        else:
            lic_price = u'(%s \u20ac)' % lic_price

        but1 = T.input(type='submit', name='submit', value='Edit')
        but2 = T.input(type='submit', name='submit', value='Delete')

        res[T.div(_class='license-key')[lic.getS(ns.licenseKey, rdf.String())]]
        res[T.div(_class='license-label')['License name']]
        res[T.div(_class='license-name')[lic.getS(ns.licenseString, rdf.String())]]
        res[T.div(_class='license-label')['Remote access users']]
        res[T.div(_class='license-user-count')[lic.getS(ns.licenseUserCount, rdf.Integer())]]
        res[T.div(_class='license-label')['Site-to-site connection (endpoints)']]
        res[T.div(_class='license-s2s-count')[lic.getS(ns.licenseSiteToSiteCount, rdf.Integer())]]
        res[T.div(_class='license-label')['State']]
        res[T.div(_class='license-state')[lic_state]]
        res[T.div(_class='license-label')['Price']]
        res[T.div(_class='license-price')[lic_price]]
        res[T.div(_class='license-clear')[u'\u00a0']]
        res[T.div(_class='license-buttons')[but1, but2]]
        res[T.div(_class='license-clear')[u'\u00a0']]
        return res
    
    def render_licenses(self, ctx, data):
        try:
            res = T.invisible()
            db = rdfdb.get_db()
            lic_sorted = rdfdb.get_licenses_sorted(db, rdfdb.get_account(db, self.get_username()))
            for i in lic_sorted:
                res[self._render_license(i)]

            return res
        except:
            _log.exception('render_licenses failed')
            raise

    def render_license_price_summary(self, ctx, data):
        try:
            db = rdfdb.get_db()
            lic_sorted = rdfdb.get_licenses_sorted(db, rdfdb.get_account(db, self.get_username()))
            total_price_enabled = gmpy.mpq(0)
            vat_pct = self.get_vat_percentage()
            vat_value = gmpy.mpq(0)
            partner_discount = gmpy.mpq(0)
            for i in lic_sorted:
                if i.getS(ns.licenseEnabled, rdf.Boolean):
                    total_price_enabled += invoicing.compute_license_price_oct2007(
                        i.getS(ns.licenseUserCount, rdf.Integer),
                        i.getS(ns.licenseSiteToSiteCount, rdf.Integer)
                        )
                else:
                    pass
                
            res = T.div(_class='pricing')
            if self.is_service_provider():
                partner_discount = invoicing.compute_partner_discount_oct2007(total_price_enabled)
                
                res[T.div(_class='pricing-label')['Total price without discounts (VAT 0%)']]
                res[T.div(_class='pricing-price')[self._format_gmpy_price(total_price_enabled)]]
                res[T.div(_class='pricing-label')['Partner discount (VAT 0%)']]
                res[T.div(_class='pricing-price')[self._format_gmpy_price(partner_discount)]]
            else:
                res[T.div(_class='pricing-label')['Total price (VAT 0%)']]
                res[T.div(_class='pricing-price')[self._format_gmpy_price(total_price_enabled)]]

            total_price_with_discounts = total_price_enabled - partner_discount
            
            # FIXME: when to show VAT?
            add_vat = True
            if add_vat:
                vat_value = total_price_with_discounts * vat_pct / gmpy.mpq(100)
                res[T.div(_class='pricing-label')['VAT (%d%%)' % vat_pct]]
                res[T.div(_class='pricing-price')[self._format_gmpy_price(vat_value)]]

            final_price = total_price_with_discounts + vat_value
            res[T.div(_class='pricing-label')['Total (incl. VAT %d%%)' % vat_pct]]
            res[T.div(_class='pricing-price')[self._format_gmpy_price(final_price)]]
            res[T.div(_class='pricing-clear')[u'\u00a0']]

            return res
        except:
            _log.exception('render_license_price_summary failed')
            raise

    def render_rdfxml_dump(self, ctx, data):
        return T.pre[rdfdb.dump_to_rdfxml()]

class PartnerSiteTestPage(PartnerSitePage):
    contentfile = 'partnersite/test.xhtml'
    uri = 'test.html'

class PartnerSiteLicensesPage(PartnerSitePage):
    contentfile = 'partnersite/licenses.xhtml'
    uri = 'licenses.html'

class PartnerSiteFloatingLicensesPage(PartnerSitePage):
    contentfile = 'partnersite/floating-licenses.xhtml'
    uri = 'floating-licenses.html'
