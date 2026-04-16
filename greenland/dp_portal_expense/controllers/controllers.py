# -*- coding: utf-8 -*-
# DP InfoSol PVT LTD. See LICENSE file for full copyright and licensing details.
from odoo import http
from collections import OrderedDict
from odoo.http import request, route, Response
import json
from odoo.exceptions import ValidationError
from odoo import _

class ExpenseRoute(http.Controller):

    def get_sort(self):
        return{
            'date': {'label': _('Date'), 'order': 'date'},
            'name':{'label':_('Name'),'order':'name'},
            'category':{'label':_('Product'),'order':'product_id'},
        }

    def get_expense_searchbar_filters(self):
        return {
            'all': {'label': _('All'), 'domain': []},
            'state': {'label': _('Status'), 'domain': [('state', '=', 'draft')]},
    }

    def get_expense_searchbar_groupby(self):
        return {
            'none': {'input': 'none', 'label': _('None')},
            'category': {'input': 'product_id', 'label': _('Product')},
            'name': {'input': 'none', 'label': _('None')},

        }
    
    @http.route('/all_expense', type="http", auth='public', website=True)
    def Expense(self,sortby=None, domain=None,filterby=None,groupby=None):
        if not sortby:
            sortby = 'date'
        searchbar_sortings = self.get_sort()
        searchbar_filters = self.get_expense_searchbar_filters()

        if not filterby:
            filterby = 'all'

        if not groupby:
            groupby = 'none'

        order = searchbar_sortings[sortby]['order']
        expense_domain = searchbar_filters[filterby]['domain'] if filterby != 'all' else []
        expense_record = http.request.env['hr.expense'].sudo().search(expense_domain,order=order)
        return request.render('dp_portal_expense.expense_data', {
            'data': expense_record,
            'searchbar_sortings':searchbar_sortings,
            'default_url':'/all_expense',
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'sortby':sortby,

        })
    #create Record Route
    @http.route('/create_record', type="http", auth='public', website=True, csrf=False)
    def create_record(self, **nr):
        user_id = request.env.user.employee_id.id
        name = nr.get('name')
        fromDate = nr.get('from_date')
        category = nr.get('category')
        vendor_id = nr.get('vendor_id')
        vat_number = nr.get('vat_number')
        invoice_reference = nr.get('invoice_reference')
        paidby = nr.get('paid_by')
        total_str = nr.get('total_expense')
        status = nr.get('status')
        total = round(float(total_str), 2) if total_str else 0.0
        print('NR = == = = ',nr)
        try:
            create_expense_record = {
                'state': 'draft',
                'name': name,
                'date': fromDate,
                'total_amount_currency': total,
                'product_id': (int(category),),
                'employee_id': user_id,
                'payment_mode': paidby,
            }
            
            # Add vendor, VAT, and invoice reference fields if provided
            if vendor_id:
                create_expense_record['vendor_id'] = int(vendor_id)
            if vat_number:
                create_expense_record['vat_number'] = vat_number
            if invoice_reference:
                create_expense_record['reference'] = invoice_reference

            record = request.env['hr.expense'].sudo().create(create_expense_record)
            print('record==============>',record)
            if nr.get('attachment_file') and nr.get('attachment_name'):
                Attachments = request.env['ir.attachment']
                attachment_id = Attachments.sudo().create({
                    'name':nr.get('attachment_name'),
                    # 'datas_fname': sr.get('attachment_name'),
                    'res_name': nr.get('attachment_name'),
                    'type': 'binary',   
                    'res_model': 'hr.expense',
                    'res_id': record.id,
                    'datas': nr.get('attachment_file'),
                })


        except Exception as e:
            print(e)

    #Fetch Data for edit Record Route
    @http.route('/edit_record', type="http", auth='public', website=True, csrf=False)
    def edit_record(self, **er):
        dic = {}
        edit_id = er.get('edit_button_id')

        if edit_id and edit_id.isdigit():
            data_id = http.request.env['hr.expense'].sudo().search([('id', '=', int(edit_id))], limit=1)
            product = data_id.product_id.id if data_id.product_id else None

            if data_id:
                response_data = {
                	'id':data_id.id,
                    'name': data_id.name,
                    'date': str(data_id.date),
                    'total_amount_currency': data_id.total_amount_currency,
                    'product_id': data_id.product_id.id,
                    'vendor_id': data_id.vendor_id.id if data_id.vendor_id else None,
                    'vat_number': data_id.vat_number or '',
                    'reference': data_id.reference or '',
                    'payment_mode': data_id.payment_mode,
                }
                return json.dumps(response_data)
            return json.dumps(dic)

    #Write data Record Route
    @http.route('/save_record', type="http", auth='public', website=True, csrf=False)
    def save_record(self, **sr):
        save_name =sr.get('name')
        save_product =sr.get('product_id')
        save_vendor_id =sr.get('vendor_id')
        save_vat_number =sr.get('vat_number')
        save_invoice_reference =sr.get('reference')
        save_total =sr.get('total_amount_currency')
        save_date =sr.get('date')
        save_paymode =sr.get('payment_mode')
        save_id = request.env['hr.expense'].sudo().search([('id','=',sr.get('id'))],limit=1)
        print(save_id)#check for record set ID
        save_data = http.request.env['hr.expense'].sudo().search([('id', '=', int(save_id))], limit=1)
        if sr.get('date'):
            save_id.sudo().write({'date': save_date})
        if sr.get('name'):
            save_id.sudo().write({'name': save_name})
        if sr.get('product_id'):
            save_id.sudo().write({'product_id': int(save_product)})
        if sr.get('vendor_id'):
            save_id.sudo().write({'vendor_id': int(save_vendor_id)})
        if sr.get('vat_number'):
            save_id.sudo().write({'vat_number': save_vat_number})
        if sr.get('reference'):
            save_id.sudo().write({'reference': save_invoice_reference})
        if sr.get('total_amount_currency'):
            save_id.sudo().write({'total_amount_currency': save_total})
        if sr.get('payment_mode'):
            save_id.sudo().write({'payment_mode':save_paymode})
        if sr.get('attachment_file') and sr.get('attachment_name'):
            Attachments = request.env['ir.attachment']
            attachment_id = Attachments.sudo().create({
                'name':sr.get('attachment_name'),
                # 'datas_fname': sr.get('attachment_name'),
                'res_name': sr.get('attachment_name'),
                'type': 'binary',   
                'res_model': 'hr.expense',
                'res_id': save_id.id,
                'datas': sr.get('attachment_file'),
            })

    #Delete Record Route
    @http.route('/delete_record', type="http", auth='public', website=True, csrf=False)
    def delete_record(self, **dr):
        dic = {}
        if dr.get('edit_button_id'):
            delete_id = request.env['hr.expense'].sudo().search(
                [('id', '=', int(dr.get('edit_button_id')))], limit=1)
            if delete_id:
                delete_id.sudo().unlink()
                dic.update({
                    'success_msg': 'Timesheet is Deleted Successfully.'
                })
        return json.dumps(dic)

    #Get Vendor VAT Route
    @http.route('/get_vendor_vat', type="http", auth='public', website=True, csrf=False)
    def get_vendor_vat(self, **vr):
        vendor_id = vr.get('vendor_id')
        if vendor_id:
            vendor = request.env['res.partner'].sudo().search([('id', '=', int(vendor_id))], limit=1)
            if vendor:
                return json.dumps({'vat': vendor.vat or ''})
        return json.dumps({'vat': ''})

    @http.route(['/my_portal/expense/preview/<int:expense_id>', '/my_portal/expense/preview/<int:expense_id>/<string:filename>'], type='http', auth='user')
    def preview_expense_report(self, expense_id, filename=None, **kwargs):
        """
        Custom route to serve the expense report PDF inline with a specific filename.
        This allows 'New Tab' preview while enforcing the correct filename.
        """
        expense_sheet = request.env['hr.expense.sheet'].browse(expense_id)
        if not expense_sheet.exists():
            return request.not_found()

        # Generate the PDF
        pdf_content, _ = request.env['ir.actions.report']._render_qweb_pdf(
            'dp_portal_expense.action_report_petty_cash_with_invoices', 
            [expense_sheet.id]
        )

        # Construct the desired filename
        # Format: Petty Cash Expenses - Employee Name - Reference
        filename = f"Petty Cash Expenses - {expense_sheet.employee_id.name} - {expense_sheet.name.replace('/', '')}.pdf"

        # Create response with inline disposition and filename
        pdfhttpheaders = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf_content)),
            ('Content-Disposition', f'inline; filename="{filename}"')
        ]
        
        return request.make_response(pdf_content, headers=pdfhttpheaders)