from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class CustomerSignatureWizard(models.TransientModel):
    _name = 'customer.signature.wizard'
    _description = 'Customer Signature Wizard'

    task_id = fields.Many2one('project.task', string='Service Ticket', required=True)
    contract_customer_id = fields.Many2one('res.partner', string='Customer', required=True, readonly=True)
    signature = fields.Binary(string='Signature', attachment=True)
    receiver_name = fields.Char(string='Receiver Name', required=True)
    receiver_position = fields.Char(string='Receiver Position')
    # use_existing = fields.Boolean(string='Use Existing Signature', default=False)
    # existing_signature_id = fields.Many2one('customer.signature', string='Existing Signature', domain="[('contract_customer_id', '=', contract_customer_id)]")

    def action_save_signature(self):
        self.ensure_one()
        if not self.signature:
            raise ValidationError(_("Please provide a signature."))
        if not self.receiver_name:
            raise ValidationError(_("Please provide the receiver's name."))
        _logger.debug("Signature data: %s", self.signature[:100] if self.signature else "No signature provided")
        vals = {
            'contract_customer_id': self.contract_customer_id.id,
            'signature': self.signature,
            'receiver_name': self.receiver_name,
            'receiver_position': self.receiver_position,
        }
        signature_id = self.env['customer.signature'].create(vals)
        self.task_id.write({'signature_id': signature_id.id})
        return {'type': 'ir.actions.act_window_close'}