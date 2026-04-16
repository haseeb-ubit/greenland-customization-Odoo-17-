# -*- coding: utf-8 -*-
from email.policy import default

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date


class CustomerDocuments(models.Model):
    _name = "customer.documents"
    _description = "Customer Documents"
    
    name = fields.Char()
    expiry_date = fields.Date("Expiry Date")
    state = fields.Selection([("Active", "Active"), ("Expired", "Expired")], default="Active", tracking=True,)
    customer_id = fields.Many2one("res.partner", "Customer")
    is_expired = fields.Boolean("Expired", compute="_compute_is_expired", store=True)

    @api.depends("expiry_date")
    def _compute_is_expired(self):
        """Mark documents as expired if expiry_date is past."""
        for record in self:
            is_expired = bool(record.expiry_date and record.expiry_date < date.today())
            record.is_expired = is_expired
            if is_expired and record.state == "Active":
                record.state = "Expired"
