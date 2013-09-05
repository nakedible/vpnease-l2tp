"""
PayPal support functionality for VPNease product web.
"""

PAYPAL_NVPAPI_VERSION = '3.2'
PAYPAL_URI_SANDBOX_SIGNATURE = 'https://api-3t.sandbox.paypal.com/nvp'
PAYPAL_URI_PRODUCTION_SIGNATURE = 'https://api-3t.paypal.com/nvp'
PAYPAL_URI_SANDBOX_CERTIFICATE = 'https://api.sandbox.paypal.com/nvp'
PAYPAL_URI_PRODUCTION_CERTIFICATE = 'https://api.paypal.com/nvp'

class Credentials:
    """API credentials for NVP requests."""
    username = None
    password = None
    signature = None

    def __init__(self, username, password, signature):
        self.username = username
        self.password = password
        self.signature = signature

sandbox_creds = Credentials('',
                            '',
                            '')

production_creds = Credentials('',
                               '',
                               '')

class PayPalResponse:
    """PayPal NVP response parsing."""
    ack = None
    timestamp = None
    correlation_id = None
    version = None
    build = None
    args = None  # method specific

    def __init__(self, XXX):
        # FIXME: check required, raise if not
        self.args = {}
    
    def is_success(self):
        # paypal nvp docs say we can process if either one of these (!)
        return self.ack in ['Success', 'SuccessWithWarning']

    def is_failure(self):
        return self.ack in ['Failure', 'FailureWithWarning', 'Warning']

class PayPalSupport:
    """Support functionality for building and sending PayPal requests."""
    creds = None
    paypal_uri = None
    
    def __init__(self, production):
        self.production = production
        if production:
            self.creds = production_creds
            self.paypal_uri = PAYPAL_URI_PRODUCTION_SIGNATURE
        else:
            self.creds = sandbox_creds
            self.paypal_uri = PAYPAL_URI_SANDBOX_SIGNATURE

    def build_nvp_request(self, method, method_args={}):
        creds = self.creds

        # SUBJECT not set
        security_params = [ ('USER', creds.username),
                            ('PWD', creds.password),
                            ('SIGNATURE', creds.signature),
                            ('VERSION', PAYPAL_NVPAPI_VERSION) ]

        body_params = [ ('METHOD', method) ]

        method_params = []
        k = method_args.keys()
        k.sort()
        for i in k:
            p_key = i
            if isinstance(p_key, unicode):
                p_key = p_key.encode('utf-8')
            if not isinstance(p_key, str):
                raise Exception('invalid key: %s' % repr(p_key))
            p_val = method_args[i]
            if isinstance(p_val, unicode):
                p_val = p_val.encode('utf-8')
            if not isinstance(p_val, str):
                raise Exception('invalid value: %s' % repr(p_val))
            method_params.append((k, method_args[k]))

        # nb: order matters
        all_params = security_params + body_params + method_params
            
        # build uri
        base = self.paypal_uri
        # FIXME

    def do_request(self, req_uri):
        """Send request, return a deferred.  Deferred returns a
        PayPalResponse in callback which also guarantees that the
        PayPal request itself succeeded.  If the PayPal request
        fails, errback is called with the PayPalResponse object in
        question (errback can of course be called with other
        errors too).
        """

        # FIXME: timeout handled here too
        d = 'FIXME'
        return d


#
#  FIXME: needs
#
#    - specific requests
#    - code for sending a https request and getting a response
#    - initial http redirection code
#


# test main
if __name__ == '__main__':
    pp = PayPalSupport(production=False)
    
    pass
