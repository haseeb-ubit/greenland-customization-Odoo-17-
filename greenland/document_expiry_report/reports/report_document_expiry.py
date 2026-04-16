from odoo import models

class DocumentExpiryReport(models.AbstractModel):
    _name = 'report.document_expiry_report.report_document_expiry'
    _description = 'Document Expiry Report'

    def _get_report_values(self, docids, data=None):
        doc_ids = data.get('doc_ids', [])
        docs = self.env['customer.documents'].browse(doc_ids)

        return {
            'doc_ids': doc_ids,
            'doc_model': 'customer.documents',
            'docs': docs,
            'start_date': data.get('start_date'),
            'end_date': data.get('end_date'),
        }
