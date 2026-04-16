from odoo import http
from odoo.http import request, content_disposition
from odoo.addons.account.controllers import portal
from odoo.addons.sale.controllers import portal as sale_portal
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import AccessError, MissingError
import urllib.parse

class PortalAccountInherit(portal.PortalAccount):

    @http.route(['/my/invoices/<int:invoice_id>'], type='http', auth="public", website=True)
    def portal_my_invoice_detail(self, invoice_id, access_token=None, report_type=None, download=False, **kw):
        try:
            invoice_sudo = self._document_check_access('account.move', invoice_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if report_type == 'pdf':
            # Redirect to the named PDF route for better filename display
            filing_ref = invoice_sudo.partner_id.ref or ''
            invoice_number = invoice_sudo.name or ''
            if filing_ref and invoice_number:
                pdf_filename = f"{filing_ref} - {invoice_number}.pdf"
            else:
                pdf_filename = f"{invoice_number}.pdf"
            
            # URL encode the filename
            encoded_filename = urllib.parse.quote(pdf_filename, safe='')
            
            # Build redirect URL with filename in path
            redirect_url = f'/my/invoices/{invoice_id}/pdf/{encoded_filename}'
            if access_token:
                redirect_url += f'?access_token={access_token}'
            
            return request.redirect(redirect_url)

        values = self._invoice_get_page_view_values(invoice_sudo, access_token, **kw)
        values['access_token'] = access_token
        return request.render("grnlnd_task.custom_invoice_download_portal", values)

    @http.route(['/my/invoices/<int:invoice_id>/pdf/<path:filename>'], type='http', auth="public", website=True)
    def portal_my_invoice_pdf_named(self, invoice_id, filename, access_token=None, **kw):
        """Custom route with filename in URL for better display in browser"""
        try:
            invoice_sudo = self._document_check_access('account.move', invoice_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # Get PDF response from parent class
        response = super(PortalAccountInherit, self).portal_my_invoice_detail(
            invoice_id, access_token=access_token, report_type='pdf', download=False, **kw
        )
        
        # Ensure inline display
        if response.headers.get('Content-Type') == 'application/pdf':
            # Decode the filename from URL
            decoded_filename = urllib.parse.unquote(filename)
            response.headers['Content-Disposition'] = f'inline; filename="{decoded_filename}"'
        
        return response

class CustomerPortalInherit(sale_portal.CustomerPortal):

    @http.route(['/my/orders/<int:order_id>'], type='http', auth="public", website=True)
    def portal_order_page(self, order_id, report_type=None, access_token=None, message=False, download=False, **kw):
        try:
            order_sudo = self._document_check_access('sale.order', order_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if report_type == 'pdf':
            # Redirect to the named PDF route for better filename display
            filing_ref = order_sudo.partner_id.ref or ''
            quotation_number = order_sudo.name or ''
            if filing_ref and quotation_number:
                pdf_filename = f"{filing_ref} - {quotation_number}.pdf"
            else:
                pdf_filename = f"{quotation_number}.pdf"
            
            # URL encode the filename
            encoded_filename = urllib.parse.quote(pdf_filename, safe='')
            
            # Build redirect URL with filename in path
            redirect_url = f'/my/orders/{order_id}/pdf/{encoded_filename}'
            if access_token:
                redirect_url += f'?access_token={access_token}'
            
            return request.redirect(redirect_url)

        return super(CustomerPortalInherit, self).portal_order_page(
            order_id, report_type=report_type, access_token=access_token, 
            message=message, download=download, **kw
        )

    @http.route(['/my/orders/<int:order_id>/pdf/<path:filename>'], type='http', auth="public", website=True)
    def portal_order_pdf_named(self, order_id, filename, access_token=None, **kw):
        """Custom route with filename in URL for better display in browser"""
        try:
            order_sudo = self._document_check_access('sale.order', order_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # Get PDF response from parent class
        response = super(CustomerPortalInherit, self).portal_order_page(
            order_id, report_type='pdf', access_token=access_token, 
            message=False, download=False, **kw
        )
        
        # Ensure inline display
        if response.headers.get('Content-Type') == 'application/pdf':
            # Decode the filename from URL
            decoded_filename = urllib.parse.unquote(filename)
            response.headers['Content-Disposition'] = f'inline; filename="{decoded_filename}"'
        
        return response


class ServiceTicketPortal(http.Controller):

    @http.route(['/report/pdf/grnlnd_task.action_report_service_ticket/<int:task_id>'], type='http', auth="user",
                website=True)
    def service_ticket_report_pdf(self, task_id, **kw):
        """Override the standard service ticket report route"""
        try:
            task_sudo = request.env['project.task'].sudo().browse(task_id)
            if not task_sudo.exists():
                return request.redirect('/my')
        except (AccessError, MissingError):
            return request.redirect('/my')

        # Custom filename logic
        filing_ref = task_sudo.ref or ''
        service_ticket_number = task_sudo.service_ticket_number or ''

        if filing_ref:
            pdf_filename = f"{filing_ref} - {service_ticket_number}.pdf"
        else:
            pdf_filename = f"- {service_ticket_number}.pdf"

        # URL encode the filename
        encoded_filename = urllib.parse.quote(pdf_filename, safe='')

        # Redirect to named route
        redirect_url = f'/service_ticket_pdf/{task_id}/{encoded_filename}'
        return request.redirect(redirect_url)

    @http.route(['/service_ticket_pdf/<int:task_id>/<path:filename>'], type='http', auth="user", website=True)
    def service_ticket_pdf_named(self, task_id, filename, **kw):
        """Serve PDF with custom filename"""
        try:
            task_sudo = request.env['project.task'].sudo().browse(task_id)
            if not task_sudo.exists():
                return request.redirect('/my')
        except (AccessError, MissingError):
            return request.redirect('/my')

        # Generate PDF using the correct Odoo 17 method
        report = request.env.ref('grnlnd_task.action_report_service_ticket')
        pdf_content, _ = report.sudo()._render_qweb_pdf('grnlnd_task.action_report_service_ticket', [task_id])

        # Decode the filename from URL
        decoded_filename = urllib.parse.unquote(filename)

        # Return PDF with custom filename
        response = request.make_response(
            pdf_content,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', f'inline; filename="{decoded_filename}"')
            ]
        )

        return response