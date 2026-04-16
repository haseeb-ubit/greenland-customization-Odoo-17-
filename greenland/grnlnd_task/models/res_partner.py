# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date


class ResPartner(models.Model):
    _inherit = "res.partner"
    name_ar = fields.Char(string="Name (Arabic)")
    street_ar = fields.Char(string="Street (Arabic)")
    city_ar = fields.Char(string="City (Arabic)")
    state_ar = fields.Char(string="State (Arabic)")
    country_ar = fields.Char(string="Country (Arabic)")
    contact_name = fields.Char(string="Contact Name")
    contact_position = fields.Char(string="Contact Position")
    customer_id = fields.Char(
        string="Customer ID",
        copy=False,
        help="Auto-generated unique customer identifier (YYYY-XXXX)"
    )

    grn_document_ids = fields.One2many("customer.documents",
                                       'customer_id',
                                       string='Customer Documents', help='Documents to be added in the contact'
                                       )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Only generate if customer_id is not already set
            if not vals.get('customer_id'):
                vals['customer_id'] = self._generate_customer_id()
        return super().create(vals_list)

    @api.onchange('customer_id')
    def _onchange_customer_id(self):
        if self.customer_id:
            existing = self.env['res.partner'].search([
                ('customer_id', '=', self.customer_id),
                ('id', '!=', self._origin.id),
            ], limit=1)
            if existing:
                warning_msg = _(
                    "Customer ID '%s' already exists for customer '%s'. "
                    "Please enter a different ID."
                ) % (self.customer_id, existing.name)
                self.customer_id = False
                return {
                    'warning': {
                        'title': _('Duplicate Customer ID'),
                        'message': warning_msg,
                    }
                }

    def _generate_customer_id(self):
        """Generate unique customer ID - sequence already includes year prefix"""
        return self.env['ir.sequence'].next_by_code('res.partner.customer.id') or f"{fields.Date.today().year}-0001"

    property_account_receivable_id = fields.Many2one(
        'account.account',
        company_dependent=True,
        string="Account Receivable",
        domain="[('account_type', '=', 'asset_receivable'), ('deprecated', '=', False)]",
        help="This account will be used instead of the default one as the receivable account for the current partner",
        required=True,
        default=lambda self: self.env['account.account'].search([('code', '=', '121000')], limit=1).id
    )

    property_account_payable_id = fields.Many2one(
        'account.account',
        company_dependent=True,
        string="Account Payable",
        domain="[('account_type', '=', 'liability_payable'), ('deprecated', '=', False)]",
        help="This account will be used instead of the default one as the payable account for the current partner",
        required=True,
        default=lambda self: self.env['account.account'].search([('code', '=', '211000')], limit=1).id
    )

    @api.model
    def customer_docs_expiry_check(self):
        """Check for expired documents, update their state, and send notifications."""
        # Find all documents where expiry_date is today or earlier and state is Active
        expired_documents = self.env["customer.documents"].search([
            ("expiry_date", "<=", date.today()),
            ("state", "=", "Active"),
        ])

        # Update the state of expired documents
        for doc in expired_documents:
            doc.state = "Expired"

            # Send notification to the customer
            if doc.customer_id:
                doc.customer_id.message_post(
                    body=_(
                        f"The document '{doc.name}' has expired on {doc.expiry_date}. Please update the document."
                    ),
                    subject="Document Expiry Notification",
                    subtype_id=self.env.ref("mail.mt_note").id,
                )

class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    iban = fields.Char(string="IBAN", tracking=True, help="International Bank Account Number")
    branch = fields.Char(string="Branch", tracking=True, help="Bank Branch Name")