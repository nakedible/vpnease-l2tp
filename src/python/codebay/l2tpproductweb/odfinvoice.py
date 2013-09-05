"""Invoice creation using ODF template.

Pretty fragile stuff, some notes:

  * Assumes "normal" namespaces (table: etc)

  * Some bad assumptions about template nodes themselves, being empty, etc.

Numeric computation is done using python-gmpy, which provides exact rational
number computation.
"""

import os
import sys
import re
import gmpy  # python-gmpy
import datetime
from codebay.l2tpproductweb import odfsupport
from codebay.l2tpproductweb import invoicing
from codebay.l2tpproductweb import invoicefile
from codebay.l2tpproductweb import invoicedata

class OdfInvoice:
    def __init__(self, invoiceInfo, invoice):
        self.re_sub = re.compile(r'\$\(([a-zA-Z0-9_]+)\)')
        self.invoiceInfo = invoiceInfo
        self.invoice = invoice
        self.vat_percentage = gmpy.mpq(22)  # FIXME
        
    def processInvoice(self, doc):
        #
        #  Compute totals etc
        #

        self.lines = self.invoice.getLines()

        total_price = gmpy.mpq(0)
        for line in self.lines:
            total_price += line.getPriceVat0()

        # total price
        self.total_price_pre_discount_vat0 = total_price

        # partner discount
        self.partner_discount = invoicing.compute_partner_discount_oct2007(self.total_price_pre_discount_vat0)

        # total price after discount
        self.total_price_vat0 = self.total_price_pre_discount_vat0 - self.partner_discount

        # VAT
        self.total_vat = self.total_price_vat0 * self.vat_percentage / gmpy.mpq(100)

        # total after discount, with VAT
        self.total_price_vat = self.total_price_vat0 + self.total_vat

        #
        #  Process replacements and generate row elements
        #
        self._process_replacements(doc)

    def _format_gmpy_price(self, x, eurosign=True):
        t = x * gmpy.mpq(100)   # 123.4567 -> 12345.67
        t = int(gmpy.digits(t)) # 12345
        full = t / 100
        part = t % 100
        esign = ''
        if eurosign:
            esign = u' \u20ac'
        if full == 0:
            return u'0,%02d%s' % (part, esign)
        else:
            return u'%d,%02d%s' % (full, part, esign)
        
    # We clone nodes here, preserving attributes, so that styles are preserved as desired
    def _clone_node(self, node):
        newcell = node.cloneNode(True)
        tmplist = list(newcell.childNodes)
        for i in tmplist:
            if i.nodeType in [i.ELEMENT_NODE, i.TEXT_NODE, i.CDATA_SECTION_NODE]:
                newcell.removeChild(i)
        return newcell

    def _process_license_table(self, doc, tablecellpara, tablecell, tablerow, table):
        # locate cells and paras for cloning
        table_cells = []
        table_paras = []
        for i in tablerow.childNodes:
            if i.localName == 'table-cell':
                table_cells.append(i)
                for j in i.childNodes:
                    if j.localName == 'p':
                        table_paras.append(j)
                        break
        print repr(table_cells)
        print repr(table_paras)
        if len(table_cells) != 5:
            raise Exception('expected 5 table cells')
        if len(table_paras) != 5:
            raise Exception('expected 5 table paras (template cells must not be empty)')
        
        def _newline():
            newrow = doc.createElement('table:table-row')
            newcell1 = self._clone_node(table_cells[0])
            newcell2 = self._clone_node(table_cells[1])
            newcell3 = self._clone_node(table_cells[2])
            newcell4 = self._clone_node(table_cells[3])
            newcell5 = self._clone_node(table_cells[4])
            newpara1 = self._clone_node(table_paras[0])
            newpara2 = self._clone_node(table_paras[1])
            newpara3 = self._clone_node(table_paras[2])
            newpara4 = self._clone_node(table_paras[3])
            newpara5 = self._clone_node(table_paras[4])
            newcell1.appendChild(newpara1)
            newcell2.appendChild(newpara2)
            newcell3.appendChild(newpara3)
            newcell4.appendChild(newpara4)
            newcell5.appendChild(newpara5)
            newrow.appendChild(newcell1)
            newrow.appendChild(newcell2)
            newrow.appendChild(newcell3)
            newrow.appendChild(newcell4)
            newrow.appendChild(newcell5)
            table.insertBefore(newrow, tablerow)
            return newpara1, newpara2, newpara3, newpara4, newpara5
        
        for line in self.lines:
            newpara1, newpara2, newpara3, newpara4, newpara5 = _newline()
            newpara1.appendChild(doc.createTextNode(line.getLicenseKey()))
            newpara2.appendChild(doc.createTextNode(line.getLicenseName()))
            newpara3.appendChild(doc.createTextNode('%d' % line.getUserCount()))
            newpara4.appendChild(doc.createTextNode('%d' % line.getS2sCount()))
            newpara5.appendChild(doc.createTextNode(self._format_gmpy_price(line.getPriceVat0())))

        table.removeChild(tablerow)

    def _process_content(self, v):
        def _do_sub(m):
            name = m.group(1).lower()
            if name == 'license_table':
                return ''
            elif name == 'service_provider_partner_only_row':
                return ''
            elif name == 'invoice_date':
                today = datetime.date.today()
                return '%i.%i.%i' % (today.day, today.month, today.year)
            elif name == 'invoice_identifier':
                return self.invoice.getBillId()
            elif name == 'invoice_reference_number':
                return self.invoice.getRefno()
            elif name == 'invoice_time_span':
                return 'Lisenssimaksut ajalta %s' % self.invoiceInfo.getPeriod()
            elif name == 'invoice_due_date':
                refday = datetime.date.today() + datetime.timedelta(days=14)
                return '%i.%i.%i' % (refday.day, refday.month, refday.year)
            elif name == 'partner_name':
                return self.invoice.getCustomer()
            elif name == 'partner_address1':
                return self.invoice.getEmail()
            elif name == 'partner_address2':
                # FIXME
                return ''
            elif name == 'partner_ytunnus_line':
                return self.invoice.getVatId()
            elif name == 'total_price_pre_discount_vat0':
                return self._format_gmpy_price(self.total_price_pre_discount_vat0)
            elif name == 'partner_discount':
                return self._format_gmpy_price(self.partner_discount)
            elif name == 'total_price_vat0':
                return self._format_gmpy_price(self.total_price_vat0)
            elif name == 'total_vat':
                return self._format_gmpy_price(self.total_vat)
            elif name == 'total_price_vat':
                return self._format_gmpy_price(self.total_price_vat)
            elif name == 'vat_percentage':
                # FIXME
                return '%d' % self.vat_percentage
            else:
                return '[UNKNOWN: %s]' % name

        def _wrapped(m):
            res = _do_sub(m)
            name = m.group(1)
            print repr('SUB: %s -> %s' % (name, res))
            return res
        
        res = re.sub(self.re_sub, _wrapped, v)
        return res
    
    def _process_replacements(self, doc):
        top = doc.documentElement

        lic_table = []     # mutability hack
        rows_to_nuke = []  # mutability hack
        
        def _recurse(n):
            for i in n.childNodes:
                if i.nodeType == i.ELEMENT_NODE:
                    _recurse(i)
                elif i.nodeType in [i.TEXT_NODE, i.CDATA_SECTION_NODE]:
                    # Nasty special case, remember this location and the table for later patching
                    tmp = i.nodeValue.strip()
                    if '$(LICENSE_TABLE)' in tmp:
                        # <table:table>
                        #   ...
                        #   <table:table-row>
                        #     <table:table-cell table:style-name="Table1.A2" office:value-type="string">
                        #       <text:p text:style-name="Table_20_Contents">$(LICENSE_TABLE)<text:line-break/>XXXXX-XXXXX-XXXXX-XXXXX-XXXXX</text:p>
                        #     </table:table-cell>
                        #     ...
                        #   </table:table-row>
                        # </table:table>

                        # gather para ref and refs to intermediate elements up to table
                        tmp = i
                        while True:
                            tmp = tmp.parentNode
                            if tmp.nodeType == tmp.ELEMENT_NODE and tmp.localName == 'p':
                                lic_table.append(tmp)
                                continue
                            if tmp.nodeType == tmp.ELEMENT_NODE and tmp.localName == 'table-cell':
                                lic_table.append(tmp)
                                continue
                            if tmp.nodeType == tmp.ELEMENT_NODE and tmp.localName == 'table-row':
                                lic_table.append(tmp)
                                continue
                            if tmp.nodeType == tmp.ELEMENT_NODE and tmp.localName == 'table':
                                lic_table.append(tmp)
                                break
                    elif '$(SERVICE_PROVIDER_PARTNER_ONLY_ROW)' in tmp:
                        # only keep this table for if service provider partner; otherwise replace with ''
                        if self.invoice.isServiceProvider():
                            pass
                        else:
                            tmp = i
                            while True:
                                tmp = tmp.parentNode
                                if tmp.nodeType == tmp.ELEMENT_NODE and tmp.localName == 'table-row':
                                    rows_to_nuke.append(tmp)
                                    break

                    i.nodeValue = self._process_content(i.nodeValue)

        # process content and get license template
        _recurse(top)

        # process license table
        if len(lic_table) == 4:
            self._process_license_table(doc, lic_table[0], lic_table[1], lic_table[2], lic_table[3])

        # nuke unwanted license table rows
        print repr('NUKE: %s' % repr(rows_to_nuke))
        for i in rows_to_nuke:
            parent = i.parentNode
            parent.removeChild(i)
                 
def _create_odf_invoice(invoiceFile, template, outdir):
    print 'Creating ODF invoice: %s, %s, %s' % (invoiceFile, template, outdir)

    print 'Reading invoice file %s' % invoiceFile
    invoiceFileReader = invoicefile.InvoiceFileReader(invoiceFile)
    invoiceInfo = invoiceFileReader.ReadInvoiceInfo()
    invoices = invoiceFileReader.ReadInvoices()
    
    for invoice in invoices:
        print 'Reading template file %s' % template
        oe = odfsupport.OdfEditor(template)
        dom = oe.getContentDom()

        print 'Processing content.xml...'
        oi = OdfInvoice(invoiceInfo, invoice)
        oi.processInvoice(dom)

        new_filename = outdir + '/' + invoiceInfo.getMonth() + '_' + invoice.getBillId() + '.odt'
        print 'Saving output file %s' % new_filename
        oe.saveContentDom(dom)
        oe.saveOdfFile(new_filename)

if __name__ == '__main__':
    _create_odf_invoice(sys.argv[1], sys.argv[2], sys.argv[3])
    
