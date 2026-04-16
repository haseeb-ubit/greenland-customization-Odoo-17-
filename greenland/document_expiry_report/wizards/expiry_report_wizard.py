from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class ExpiryReportWizard(models.TransientModel):
    _name = 'document.expiry.report.wizard'
    _description = 'Document Expiry Report Wizard'

    start_date = fields.Date(string='Start Date', required=True)
    end_date = fields.Date(string='End Date', required=True)

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for record in self:
            if record.start_date and record.end_date and record.start_date > record.end_date:
                raise ValidationError('Start date must be before end date!')

    def action_generate_report(self):
        _logger.info("Starting report generation with dates: %s to %s", self.start_date, self.end_date)
        
        CustomerDocs = self.env['customer.documents']
        docs = CustomerDocs.get_all_documents_in_range(
            self.start_date.strftime('%Y-%m-%d'),
            self.end_date.strftime('%Y-%m-%d')
        )
        
        _logger.info("Found %s documents", len(docs['docs']))
        for doc in docs['docs']:
            _logger.info("Document: ID=%s, Name=%s, Customer=%s, Expiry=%s", 
                        doc.id, doc.name, doc.customer_id.name, doc.expiry_date)

        data = {
            'doc_ids': docs['docs'].ids,
            'doc_model': 'customer.documents',
            'docs': docs['docs'],
            'start_date': docs['start_date'],
            'end_date': docs['end_date'],
        }
        _logger.info("Sending data to report: %s", data)

        return self.env.ref('document_expiry_report.action_document_expiry_report').report_action(
            self, data=data, config=False
        )

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}