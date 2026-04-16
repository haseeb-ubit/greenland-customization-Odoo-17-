# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'
    
    is_error_invoice = fields.Boolean(
        string="Error Invoice",
        default=False,
        help="Mark this reversal as an error. The original reversed invoice will be hidden from customer statements."
    )
    
    def _prepare_default_reversal(self, move):
        """Override to add is_error_invoice to the reversed move"""
        vals = super()._prepare_default_reversal(move)
        vals['is_error_invoice'] = self.is_error_invoice
        return vals
