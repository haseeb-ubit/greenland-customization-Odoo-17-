from odoo import http
from odoo.http import request


class ServiceTicketShareController(http.Controller):
    @http.route(['/grnlnd/service_ticket/share/<int:task_id>/<string:token>'], type='http', auth='public', website=True)
    def share_ticket(self, task_id, token, **kwargs):
        task = request.env['project.task'].sudo().browse(task_id)
        if not task or not task.exists() or task.share_token != token:
            return request.not_found()

        # Render the portal-like page for service ticket download
        values = {
            'task': task,
            'token': token,
        }
        html = request.env['ir.ui.view']._render_template('grnlnd_task.service_ticket_portal_page', values)
        return request.make_response(html, headers=[('Content-Type', 'text/html; charset=utf-8')])

    @http.route(['/grnlnd/service_ticket/download/<int:task_id>/<string:token>'], type='http', auth='public', website=True)
    def download_ticket_pdf(self, task_id, token, **kwargs):
        task = request.env['project.task'].sudo().browse(task_id)
        if not task or not task.exists() or task.share_token != token:
            return request.not_found()

        # Generate the PDF of the service ticket report
        pdf = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'grnlnd_task.report_service_ticket_template',
            res_ids=task.id
        )[0]
        headers = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', 'attachment; filename=service_ticket_%s.pdf' % (task.service_ticket_number or task.id))
        ]
        return request.make_response(pdf, headers=headers)

