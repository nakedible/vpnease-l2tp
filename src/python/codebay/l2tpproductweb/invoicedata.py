""" Invoice data structures.
"""

import gmpy
from codebay.l2tpproductweb import invoicing

class InvoiceLine:
    def __init__(self, license_key, license_name, user_count, s2s_count):
        self.license_key = license_key
        self.license_name = license_name
        self.user_count = user_count
        self.s2s_count = s2s_count

    def getLicenseKey(self):
        return self.license_key

    def getLicenseName(self):
        return self.license_name

    def getUserCount(self):
        return self.user_count

    def getS2sCount(self):
        return self.s2s_count

    def getPriceVat0(self):
        intval = invoicing.compute_license_price_oct2007(self.user_count, self.s2s_count)
        return gmpy.mpq(intval)

class VpneaseInvoice:
    def __init__(self, billId, refno, customer, email, vatId, serviceProvider):
        self.billId = billId
        self.refno = refno
        self.customer = customer
        self.email = email
        self.vatId = vatId
        self.serviceProvider = serviceProvider
        self.invoiceLines = []
        
    def getBillId(self):
        return self.billId
        
    def getRefno(self):
        return self.refno
        
    def getCustomer(self):
        return self.customer
        
    def getEmail(self):
        return self.email
    
    def getVatId(self):
        return self.vatId
        
    def isServiceProvider(self):
        return self.serviceProvider
        
    def getLines(self):
        return self.invoiceLines 
        
    def addLine(self, line):
        self.invoiceLines.append(line)
               
class InvoiceInfo:
    def __init__(self, month, period):
        self.month = month
        self.period = period
    
    def getMonth(self):
        return self.month
        
    def getPeriod(self):
        return self.period 
