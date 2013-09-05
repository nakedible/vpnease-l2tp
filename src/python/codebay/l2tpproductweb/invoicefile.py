"""Provides class for reading invoice information from a text file.
   Current text file format can be found from the invoicing folder (e.g. 2008_10_invoices.txt)
   Check the latest invoice file. 
"""

import os
from codebay.l2tpproductweb import invoicedata  

class InvoiceFileReader:
    def __init__(self, filename):
        self.filename = filename
        
    def ReadInvoiceInfo(self):
        f = None
        f = open(self.filename, 'r')
        try:
            info = f.readline().split(';')
        finally:
            if f is not None:
                f.close()
                f = None
        return invoicedata.InvoiceInfo(info[0].strip(), info[1].strip())
        
    def ReadInvoices(self):
        f = None
        f = open(self.filename, 'r')
        invoices = []
        currInvoice = None
        
        try:
            custInfoStarted = False
            while f:
                line = f.readline().strip()
                if (len(line) == 0):
                    break
                # Customers are separated with '-'
                if (line == '-'):
                    custInfoStarted = True
                    if ( currInvoice != None ):
                        invoices.append(currInvoice)
                        
                    custInfo = f.readline().strip().split(';')
                    currInvoice = invoicedata.VpneaseInvoice(custInfo[0], custInfo[1], custInfo[2], custInfo[3], custInfo[4], (custInfo[5] == 'True'))
                else:
                    if (custInfoStarted):
                        lineItems = line.split(';')
                        currInvoice.addLine(invoicedata.InvoiceLine(lineItems[0], lineItems[1], int(lineItems[2]), int(lineItems[3])))
                        
            if ( currInvoice != None ):
                invoices.append(currInvoice)         
        finally:
            if f is not None:
                f.close()
                f = None    
        return invoices
    
