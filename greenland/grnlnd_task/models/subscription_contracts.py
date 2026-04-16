from odoo import fields, models

class SubscriptionContracts(models.Model):
    _inherit = 'subscription.contracts'

    customer_id = fields.Char(related='partner_id.customer_id', string="Customer ID", readonly=True, store=True)
    ref = fields.Char(related='partner_id.ref', string="Filing Reference", readonly=True, store=True)