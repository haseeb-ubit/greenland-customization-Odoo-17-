from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    partner_vat = fields.Char(string='Vendor VAT')


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    partner_vat = fields.Char(string='Vendor VAT')
