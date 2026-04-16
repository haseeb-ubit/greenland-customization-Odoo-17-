# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountPaymentCustom(models.Model):
    _inherit = 'account.payment'

    customer_id = fields.Many2one(
        'res.partner',
        string='Customer',
        domain="[('x_studio_contact_type', '=', 'Customer'), ('is_company', '=', True)]",
        copy=False,
    )

    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        domain="[('x_studio_contact_type', '=', 'Vendor'), ('is_company', '=', True)]",
        copy=False,
    )

    @api.onchange('customer_id')
    def _onchange_customer_id(self):
        """When customer is selected in generic payments, update partner_id"""
        if self.customer_id and self._context.get('payment_context') != 'vendor':
            self.partner_id = self.customer_id

    @api.onchange('vendor_id')
    def _onchange_vendor_id(self):
        """When vendor is selected in generic payments, update partner_id"""
        if self.vendor_id and self._context.get('payment_context') != 'customer':
            self.partner_id = self.vendor_id

    @api.onchange('partner_id')
    def _onchange_partner_id_sync(self):
        """Sync partner_id to customer_id or vendor_id based on context"""
        if self.partner_id:
            context = self._context.get('payment_context')
            if context == 'customer':
                self.customer_id = self.partner_id
            elif context == 'vendor':
                self.vendor_id = self.partner_id
