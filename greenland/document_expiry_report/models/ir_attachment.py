from odoo import models, fields

class IrAttachment(models.Model):
    _inherit = 'ir.attachment'
 
    expiry_date = fields.Date(string='Expiry Date')
    partner_id = fields.Many2one('res.partner', string='Customer') 