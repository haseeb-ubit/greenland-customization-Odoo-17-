from odoo import models, fields, api
from datetime import datetime, date

class CustomerDocuments(models.Model):
    _inherit = "customer.documents"
    
    # Inherit existing fields
    name = fields.Char(string='Document Name')
    customer_id = fields.Many2one('res.partner', string='Customer')
    expiry_date = fields.Date(string='Expiry Date')
    state = fields.Selection([
        ('Active', 'Active'),
        ('Expired', 'Expired')
    ], string='Status', default='Active')

    def get_documents_by_date_range(self, start_date, end_date):
        """Get documents within a specific date range, sorted by expiry_date (oldest to newest)."""
        domain = [
            ('expiry_date', '>=', start_date),
            ('expiry_date', '<=', end_date)
        ]
        return self.search(domain, order='expiry_date asc')

    def get_document_data(self):
        """Get formatted document data for reporting."""
        return {
            'name': self.name or 'N/A',
            'customer_name': self.customer_id.name or 'N/A',
            'expiry_date': self.expiry_date.strftime('%d-%m-%Y') if self.expiry_date else 'N/A',
            'state': self.state or 'N/A'
        }

    @api.model
    def get_all_documents_in_range(self, start_date, end_date):
        """Get all documents within date range with formatted dates."""
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            formatted_start_date = start_date_obj.strftime('%d-%m-%Y')
            formatted_end_date = end_date_obj.strftime('%d-%m-%Y')
        except (ValueError, TypeError):
            formatted_start_date = 'N/A'
            formatted_end_date = 'N/A'

        documents = self.get_documents_by_date_range(start_date, end_date)
        return {
            'docs': documents,
            'start_date': formatted_start_date,
            'end_date': formatted_end_date
        }