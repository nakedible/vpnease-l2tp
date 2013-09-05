"""RDF definitions for initial RDF-based product web."""
__docformat__ = 'epytext en'

from codebay.common import rdf

ns_codebay = rdf.NS('http://purl.org/NET/codebay/1.0/')

ns_l2tp_product_web = rdf.NS(
    ns_codebay['l2tp-product-web/1.0/'],

    # Global root for product web database
    l2tpProductWebGlobalRoot = None,
    L2tpProductWebGlobalRoot = None,

    creationTime = None,               

    accounts = None,
    Accounts = None,
    account = None,
    Account = None,
    
    licenses = None,
    Licenses = None,
    license = None,
    License = None,
    
    # account properties
    username = None,
    passwordSalt = None,
    passwordSha1 = None,   # SHA1(salt | ':' | password), all UTF-8
    companyName = None,
    companyCountry = None,
    companyBusinessId = None,
    companyEmail = None,
    companyWebSite = None,
    companyPhoneNumber = None,
    companyDescription = None,
    companyEuMember = None,
    companyEuVatId = None,
    contactName = None,
    contactEmail = None,
    contactPhoneNumber = None,
    howDidYouHearOfUs = None,
    comments = None,

    # account billing properties 
    paypalRecurringPayment = None, PaypalRecurringPayment = None,

    # paypalRecurringPayment properties - see PayPal NVP reference, pp. 85
    # does not have all properties; node created when recurring payment
    # has been confirmed
    buyerPaypalId = None,           # (PAYERID)
    buyerEmail = None,              # (EMAIL)
    buyerStatus = None,             # (PAYERSTATUS)
    buyerCountryCode = None,        # (COUNTRYCODE)
    buyerBusinessName = None,       # (BUSINESS)
    startDate = None,               # (PROFILESTARTDATE)
    reference = None,               # (PROFILEREFERENCE)
    profileId = None,               # (PROFILEID)
    amount = None,                  # in euros (AMT)
    taxAmount = None,               # in euros (TAXAMT)
    initialAmount = None,           # in euros (INITAMT)
    creditCardType = None,          # text (CREDITCARDTYPE)
    creditCardCensored = None,      # card number, 6 first and 4 last digits shown (e.g. 123456******3456) (ACCT)
    creditCardExpiry = None,        # expiry date (EXPDATE)
    miscInfo = None,                # misc dumped textual information, for admin use (no rdf data for everything)
    
    # license properties
    licenseKey = None,
    licenseString = None,
    licenseUserCount = None,
    licenseSiteToSiteCount = None,
    licenseEnabled = None,
    # account property links to related account
)
