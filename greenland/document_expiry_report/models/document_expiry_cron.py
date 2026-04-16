from odoo import models, fields, api
from datetime import datetime, timedelta
import logging
import base64

_logger = logging.getLogger(__name__)

class DocumentExpiryCronJob(models.Model):
    _name = 'document.expiry.cron'
    _description = 'Document Expiry Cron Job Manager'

    @api.model
    def send_document_expiry_report(self):
        """
        Cron job method to generate and send document expiry report.
        This method will be called every 30 days automatically.
        """
        try:
            _logger.info("Starting automated document expiry report generation")

            # Calculate date range: today and next 30 days
            today = datetime.today().date()
            end_date = today + timedelta(days=30)

            # Get documents that are expired or expiring in next 30 days
            CustomerDocs = self.env['customer.documents']
            docs = CustomerDocs.search([
                '|',  # OR condition for expired or soon-to-expire documents
                ('expiry_date', '<', today),  # Expired documents
                '&',  # AND condition for active documents expiring soon
                ('expiry_date', '>=', today),
                ('expiry_date', '<=', end_date),  # Documents expiring in next 30 days
            ])

            _logger.info(f"Found {len(docs)} documents for expiry report: {docs.mapped('name')}, IDs: {docs.ids}")

            report_data = {
                'doc_ids': docs.ids,
                'doc_model': 'customer.documents',
                'docs': docs,
                'start_date': today.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d'),
            }
            _logger.info(f"Report data: {report_data}")

            # Use the single report action
            report_action = self.env.ref('document_expiry_report.action_document_expiry_report')
            _logger.info(f"Using report action: {report_action.name}, model: {report_action.model}, report_name: {report_action.report_name}")
            pdf_content, _ = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
                report_action.report_name,
                res_ids=docs.ids if docs else None,
                data=report_data
            )

            # Create attachment
            attachment = self.env['ir.attachment'].sudo().create({
                'name': f'Document_Expiry_Report_{today.strftime("%Y%m%d")}.pdf',
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'mimetype': 'application/pdf',
                'res_model': 'customer.documents',
                'res_id': 0,
            })
            _logger.info(f"Attachment created: {attachment.name}")

            # Send email using the email template created from frontend
            self._send_expiry_report_email(attachment, today, end_date, len(docs))

            _logger.info("Document expiry report sent successfully")

        except Exception as e:
            _logger.error(f"Error in document expiry cron job: {str(e)}")
            raise

    def _send_expiry_report_email(self, attachment, start_date, end_date, doc_count):

        try:
            # Get the email template (to be created from frontend)
            template = self.env.ref('document_expiry_report.email_template_document_expiry_report',
                                   raise_if_not_found=False)

            if not template:
                _logger.warning(
                    "Email template 'email_template_document_expiry_report' not found. Please create it from frontend.")
                return

            # Prepare email context for variable replacement
            email_context = {
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d'),
                'document_count': doc_count,
                'report_generated_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }

            # Create a temporary record for template rendering
            temp_record = self.env['document.expiry.cron'].create({})

            try:
                # Send email with attachment
                mail_id = template.sudo().send_mail(
                    temp_record.id,
                    force_send=True,
                    email_values={
                        'attachment_ids': [(6, 0, [attachment.id])],
                        'email_from': self.env.company.email or 'noreply@company.com',
                    }
                )

                # Update email with custom context
                if mail_id:
                    mail_record = self.env['mail.mail'].sudo().browse(mail_id)
                    if mail_record.subject:
                        mail_record.subject = mail_record.subject.format(**email_context)
                    if mail_record.body_html:
                        mail_record.body_html = mail_record.body_html.format(**email_context)
                    _logger.info(f"Expiry report email sent with {doc_count} documents")

            finally:
                # Clean up temporary record
                temp_record.unlink()

        except Exception as e:
            _logger.error(f"Error sending expiry report email: {str(e)}")
