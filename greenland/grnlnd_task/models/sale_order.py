# -*- coding: utf-8 -*-


from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError, AccessError
from odoo.tools.safe_eval import safe_eval
from odoo.osv.expression import AND
from datetime import date
from datetime import timedelta
from odoo.tools import float_is_zero, format_amount, format_date, html_keep_url, is_html_empty
import logging
from lxml import html
_logger = logging.getLogger(__name__)

INVOICE_STATUS = [
    ('upselling', 'Upselling Opportunity'),
    ('invoiced', 'Fully Invoiced'),
    ('to invoice', 'To Invoice'),
    ('no', 'Nothing to Invoice'),
    ('convert contract','Converted to Contract')
]

SALE_ORDER_STATE = [
    ('draft', "Draft"),
    ('sent', "Pending Approval"),
    ('sale', "Sales Order"),
    ('cancel', "Cancelled"),
    ('convert contract','Converted to Contract'),
    ('completed', 'Completed')
]

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    quotation_version= fields.Char(string="Quotation Version")
    contact_name = fields.Char(string="Contact Name")
    contact_position = fields.Char(string="Contact Position")
    contact_number = fields.Char(string="Contact Number")
    contact_email = fields.Char(string="Contact Email")

    state = fields.Selection(
        selection=SALE_ORDER_STATE,
        string="Status",
        readonly=True, copy=False, index=True,
        tracking=3,
        default='draft')

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string="Customer",
        required=True, change_default=True, index=True,
        tracking=1,
        check_company=True,
        domain=lambda self: [('is_company', '=', True)]
    )
    is_contract_quotation = fields.Boolean(
        string="Is Contract Quotation",
        default=False,
        help="Flag to differentiate contract quotations from regular quotations"
    )
    order_type = fields.Selection([
        ('Non Hazardous', 'Non Hazardous'),
        ('Hazardous', 'Hazardous'),
    ], string='Order Type', default='Non Hazardous', copy=False, tracking=True,
        help='Type of order')
    ticket_task_count = fields.Integer(store=True,
                                       compute='_compute_task_count',
                                       string='Task count',
                                       help='Number of task tickets generated')
    terms_and_conditions_ids = fields.Many2many(
        'terms_and_conditions',
        'terms_conditions_sale_order_rel',
        'sale_order_id',
        'terms_condition_id',
        string="Terms and Conditions"
    )
    category = fields.Many2one(
        'terms.category',
        string="Terms Category",
        related='terms_and_conditions_ids.category',
        store=True,
        readonly=True
    )
    
    quotation_validity_days = fields.Integer(
        string="Quotation Validity Days",
        compute='_compute_quotation_validity_days',
        help="Number of days between creation date and validity date"
    )
    invoice_count = fields.Integer(
        string='Invoice Count', compute='_compute_invoice_count', store=True,
        help="Number of invoices linked to this sale order."
    )
    
    @api.depends('validity_date', 'create_date')
    def _compute_quotation_validity_days(self):
        for order in self:
            if order.validity_date and order.create_date:
                # Convert create_date to date if it's datetime
                create_date = order.create_date.date() if hasattr(order.create_date, 'date') else order.create_date
                validity_date = order.validity_date
                
                # Calculate the difference in days
                if validity_date and create_date:
                    delta = validity_date - create_date
                    order.quotation_validity_days = delta.days
                else:
                    order.quotation_validity_days = 0
            else:
                order.quotation_validity_days = 0

    invoice_status = fields.Selection(
        selection=INVOICE_STATUS,
        string="Invoice Status",
        compute='_compute_invoice_status',
        store=True)

    contract_approved = fields.Boolean(
        string="Contract Approved", default=False,store=True)

    calculate_totals = fields.Boolean(
        string="Calculate Totals", default=True, store=True)

    note = fields.Html(
        string="Terms and conditions",
        store=True, readonly=False)

    note_lines = fields.Text(
        string="Terms as list",
        compute='_compute_note_lines',
        store=False
    )

    customer_id = fields.Char(related='partner_id.customer_id', string="Customer ID", readonly=True, store=True)
    ref = fields.Char(related='partner_id.ref', string="Filing Reference", readonly=True, store=True)

    @api.depends('partner_id')
    def _compute_note_lines(self):
        if self.note:
            for order in self:
                tree = html.fromstring(order.note)
                term_lines = [line.strip() for line in tree.xpath('//text()') if line.strip()]
                proper_terms = ''
                for line in term_lines:
                    proper_terms = proper_terms + '\n' + line
                order.note_lines=proper_terms
        else:
            self.note_lines = ''
    def action_preview_sale_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': self.get_portal_url(report_type='pdf'),
        }

    @api.onchange('order_type')
    def _onchange_order_type_field(self):
        if self.order_type:
            # Clear the order lines using the correct field name
            self.order_line = [(5, 0, 0)]  # Removes all records  # Removes all records

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for order in self:
            order.invoice_count = len(order.invoice_ids)

    def _compute_invoice_status(self):
        """Override if custom logic is needed for invoice_status."""
        super(SaleOrder, self)._compute_invoice_status()

        confirmed_orders = self.filtered(lambda so: so.state == 'sale')
        (self - confirmed_orders).invoice_status = 'no'
        if not confirmed_orders:
            return
        lines_domain = [('is_downpayment', '=', False), ('display_type', '=', False)]
        line_invoice_status_all = [
            (order.id, invoice_status)
            for order, invoice_status in self.env['sale.order.line']._read_group(
                lines_domain + [('order_id', 'in', confirmed_orders.ids)],
                ['order_id', 'invoice_status']
            )
        ]
        for order in confirmed_orders:
            line_invoice_status = [d[1] for d in line_invoice_status_all if d[0] == order.id]
            if order.state != 'sale':
                order.invoice_status = 'no'
            elif any(invoice_status == 'to invoice' for invoice_status in line_invoice_status):
                if any(invoice_status == 'no' for invoice_status in line_invoice_status):
                    # If only discount/delivery/promotion lines can be invoiced, the SO should not
                    # be invoiceable.
                    invoiceable_domain = lines_domain + [('invoice_status', '=', 'to invoice')]
                    invoiceable_lines = order.order_line.filtered_domain(invoiceable_domain)
                    special_lines = invoiceable_lines.filtered(
                        lambda sol: not sol._can_be_invoiced_alone()
                    )
                    if invoiceable_lines == special_lines:
                        order.invoice_status = 'no'
                    else:
                        if self.is_contract_quotation:
                            order.invoice_status = 'convert contract'
                            order.state = 'convert contract'
                        else:
                            order.invoice_status = 'to invoice'
                else:
                    if self.is_contract_quotation:
                        order.invoice_status = 'convert contract'
                        order.state = 'convert contract'
                    else:
                        order.invoice_status = 'to invoice'
            elif line_invoice_status and all(
                    invoice_status == 'invoiced' for invoice_status in line_invoice_status):
                order.invoice_status = 'invoiced'
            elif line_invoice_status and all(
                    invoice_status in ('invoiced', 'upselling') for invoice_status in line_invoice_status):
                order.invoice_status = 'upselling'
            else:
                order.invoice_status = 'no'

    def action_view_invoice(self):
        self.ensure_one()
        invoice_ids = []
        invoices = self.env['account.move'].search([('invoice_origin', '=', self.name)])
        invoice_ids.extend(invoices.ids)
        if not invoice_ids:
            raise UserError(_("No invoices linked to this Sale Order."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices'),
            'view_mode': 'tree,form',
            'res_model': 'account.move',
            'domain': [('id', 'in', invoice_ids)],
            'context': {'create': False},
        }

    invoice_state = fields.Selection(
        string="Invoice State",
        selection=[
            ('draft', 'Draft Invoice'),
            ('posted', 'Invoice Confirmed'),
            ('cancel', 'Cancelled'),
            ('not', 'Not Invoiced'),
        ],
        compute='_compute_invoice_state',
        default='not'
    )
    task_sale_order_id = fields.Many2one('sale.order', string='Sales Order',
                                         help="Sales order to which the project is linked.")

    @api.depends('invoice_ids.state')
    def _compute_invoice_state(self):
        for task in self:
            task.invoice_state = 'not'
            if task.invoice_id:
                # Map the states from account.move to custom labels
                if task.invoice_id.state == 'draft':
                    task.invoice_state = 'draft'
                elif task.invoice_id.state == 'posted':
                    task.invoice_state = 'posted'
                elif task.invoice_id.state == 'cancel':
                    task.invoice_state = 'cancel'
                else:
                    task.invoice_state = 'unknown'
            else:
                task.invoice_state = 'not'

    @api.depends('partner_id')
    def _compute_task_count(self):
        for record in self:
            record.ticket_task_count = self.env['project.task'].search_count([
                ('task_sale_order_id', '=', record.id)])

    def action_create_task_ticket(self):
        self.ensure_one()
        # Create project task
        task = self.env['project.task'].create({
            'name': f'Task for Sale Order {self.name}',
            'partner_id': self.partner_id.id,
            'task_sale_order_id': self.id,
            'contract_type': self.order_type,
            'contract_customer_id':self.partner_id.id

        })
        self.ticket_task_count = self.env['project.task'].search_count([
            ('task_sale_order_id', '=', self.id)])

        # Optional: Add a smart button or action to open the created task
        return {
            'type': 'ir.actions.act_window',
            'name': 'Project Task',
            'res_model': 'project.task',
            'res_id': task.id,
            'domain': [('task_sale_order_id', '=', self.id), ('contract_type', '=', self.order_type)],
            "context": {'default_contract_type': self.order_type},
            'view_mode': 'form',
            'target': 'current',
        }

    def action_get_task(self):
        self.ensure_one()
        tree_view_id = self.env.ref('grnlnd_task.view_task_tree3').id
        form_view_id = self.env.ref('project.view_task_form2').id
        self.ticket_task_count = self.env['project.task'].search_count([
            ('task_sale_order_id', '=', self.id)])
        return {
            'type': 'ir.actions.act_window',
            'name': _('Service Tickets'),
            'view_mode': 'tree',
            'res_model': 'project.task',
            'views': [(tree_view_id, 'tree'), (form_view_id, 'form')],
            'domain': [('task_sale_order_id', '=', self.id)],
            "context": {'default_contract_type': self.order_type},
            'target': 'current',
        }
    # sale.view_order_form

    # tasks_ids = fields.Many2many('project.task', compute='_compute_tasks_ids', search='_search_tasks_ids', string='Tasks associated to this sale')
    # tasks_count = fields.Integer(string='Tasks', compute='_compute_tasks_ids', groups="project.group_project_user")

    def action_convert_to_contract(self):
        if self.contract_approved==False:
            self.contract_approved = True
        self.ensure_one()
        self.state = 'sale'
        self.state = 'convert contract'
        self.invoice_status = 'convert contract'
        contract = self.env['subscription.contracts'].create({
            'name': 'New',
            'partner_id': self.partner_id.id,
            'amount_total': sum(line.price_total for line in self.order_line),
            'note': self.note,
            'contract_type': self.order_type,
            'payment_terms_id': self.payment_term_id.id
        })

        for line in self.order_line:
            self.env['subscription.contracts.line'].create({
                'subscription_contract_id': contract.id,
                'product_id': line.product_id.id,
                'description': line.name,
                'location': line.location.id,
                'product_uom_qty': line.product_uom_qty,
                'product_uom_id': line.product_uom.id,
                'price_unit': line.price_unit,
                'tax_ids': [(6, 0, line.tax_id.ids)],
                'discount': line.discount,
                'sub_total': line.price_total,
                'service_type': line.service_type
            })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Subscription Contract',
            'res_model': 'subscription.contracts',
            'res_id': contract.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def open_generate_invoice_wizard(self):
        """Open the wizard for generating an invoice with date inputs."""
        first_day_of_month = date.today().replace(day=1)

        return {
            'name': 'Generate Invoice',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.invoice.wizard',
            'view_mode': 'form',
            'target': 'new',  # Opens the form in a modal
            'context': {
                'default_start_date': first_day_of_month,
                'default_end_date': fields.Date.context_today(self),
                'active_ids': self.ids,
            }
        }

    def fetch_service_tickets(self, start_date, end_date):
        """Fetch all service tickets associated with this sale order."""
        return self.env["project.task"].search([
            ('task_sale_order_id', '=', self.id),
            ('date_deadline', '>=', start_date),
            ('date_deadline', '<=', end_date),
        ])

    def fetch_uninvoiced_service_tickets(self, start_date, end_date):
        """Fetch service tickets that have not yet been invoiced."""
        return self.env["project.task"].search([
            ('task_sale_order_id', '=', self.id),
            ('date_deadline', '>=', start_date),
            ('date_deadline', '<=', end_date),
            ('state', '!=', '05_invoiced'),
        ])

    def generate_invoice_line_items(self, service_tasks, confirmed_invoice_ids=[]):
        """Generate invoice line items from service tasks."""
        result = []

        # Map service lines by product ID
        service_line_map = {}
        for task in service_tasks:
            for line_item in task.contract_service_ids:
                if (line_item.name.id,line_item.location.id) not in service_line_map:
                    service_line_map[line_item.name.id,line_item.location.id] = []
                service_line_map[line_item.name.id,line_item.location.id].append(line_item)

        # Get all invoice lines from confirmed invoices
        invoice_lines = self.env['account.move.line'].search([
            ('move_id', 'in', confirmed_invoice_ids)
        ])

        invoiced_quantities = {
            line.product_id.id: line.quantity for line in invoice_lines
        }

        for order_line in self.order_line:
            # if service_line_map:
            service_lines = service_line_map.get((order_line.product_id.id,order_line.location.id), [])
            service_quantity = sum(line.quantity for line in service_lines)

            # Get the invoiced quantity for the current product
            invoiced_quantity = invoiced_quantities.get(order_line.product_id.id, 0.0)
            # Determine the final invoice quantity
            if invoiced_quantity > 0:
                final_quantity = service_quantity
            else:
                total_quantity = service_quantity + invoiced_quantity

                if total_quantity < order_line.product_uom_qty:
                    if order_line.service_type == 'Optional':
                        final_quantity = order_line.product_uom_qty - total_quantity
                    else:
                        final_quantity = order_line.product_uom_qty
                else:
                    final_quantity = total_quantity

            # Skip optional services with no service lines
            if not service_lines and order_line.service_type == 'Optional':
                continue
            # product_uom_id = (
            #     service_lines[0].product_uom_id.id
            #     if service_lines and service_lines[0].product_uom_id
            #     else order_line.product_id.uom_id.id
            # )
            # Add invoice line if quantity > 0
            if final_quantity > 0:
                result.append((0, 0, {
                    'product_id': order_line.product_id.id,
                    # 'product_uom_id': product_uom_id,
                    'name': order_line.name,
                    'quantity': final_quantity,
                    'price_unit': order_line.price_unit,
                    'tax_ids': [(6, 0, order_line.tax_id.ids)],
                    'discount': order_line.discount,
                    'location': order_line.location.id,
                }))

        return result

    def action_generate_invoice(self, start_date=None, end_date=None):
        """Generate an invoice for this sale order within the specified period."""
        if not start_date or not end_date:
            raise UserError(_("Start date and End date are required."))

        start_datetime = fields.Datetime.to_string(start_date)
        end_datetime = fields.Datetime.to_string(end_date)

        service_tasks = self.fetch_service_tickets(end_date=end_datetime, start_date=start_datetime)

        invoice_line_items = []
        confirmed_invoice_ids = []
        uninvoiced_tasks = []

        existing_invoices = self.env['account.move'].search([
            ('invoice_origin', '=', self.name),
            ('move_type', '=', 'out_invoice'),
            ('invoice_date', '>=', start_date),
            ('invoice_date', '<=', end_date),
        ])

        # # Handle Confirmed Invoices
        last_confirmed_invoice_date = None
        for invoice in existing_invoices:
            if invoice.state == 'posted':
                if not last_confirmed_invoice_date or invoice.invoice_date > last_confirmed_invoice_date:
                    last_confirmed_invoice_date = invoice.invoice_date
                confirmed_invoice_ids.append(invoice.id)

        for invoice in existing_invoices.filtered(lambda inv: inv.state == 'draft'):
            # invoice.unlink()
            self.env["account.move"].sudo().browse(invoice.id).unlink()
            self.invoice_count = self.env['account.move'].search_count([('invoice_origin', '=', self.id)])

        if service_tasks:
            uninvoiced_tasks = self.fetch_uninvoiced_service_tickets(start_date, end_date)
            invoice_line_items = self.generate_invoice_line_items(uninvoiced_tasks, confirmed_invoice_ids)

        elif not service_tasks and not confirmed_invoice_ids:
            for order_line in self.order_line:
                if order_line.service_type == "Required":
                    invoice_line_items.append((0, 0, {
                        'product_id': order_line.product_id.id,
                        'name': order_line.name,
                        'quantity': order_line.product_uom_qty, #Qty Changes
                        'price_unit': order_line.price_unit,
                        'tax_ids': [(6, 0, order_line.tax_id.ids)],
                        'discount': order_line.discount,
                        'location': order_line.location.id
                    }))

        if not invoice_line_items:
            raise UserError(_('No service tickets available to be invoiced.'))

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': fields.Date.today(),
            'invoice_origin': self.name,
            'invoice_payment_term_id': self.payment_term_id.id if self.payment_term_id else None,
            'currency_id': self.currency_id.id,
            'invoice_line_ids': invoice_line_items,
            'start_date': start_date,
            'end_date': end_date,
        })
        if uninvoiced_tasks:
            for ticket in uninvoiced_tasks:
                ticket.write({'invoice_id': invoice.id, 'state': '07_before_invoiced'})

        # Update invoice count
        self.invoice_count = self.env['account.move'].search_count([('invoice_origin', '=', self.name)])


        return {
            'type': 'ir.actions.act_window',
            'name': _('Generated Invoice'),
            'view_mode': 'form',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'target': 'current',
        }

    def action_quotation_send(self):
        """ Opens a wizard to compose an email, with relevant mail template loaded by default """

        if self.is_contract_quotation:
            for record in self:
            # Search for other active contracts of the same type for this customer
                existing_contract = self.env['subscription.contracts'].search([
                        ('partner_id', '=', record.partner_id.id),
                        ('contract_type', '=', record.order_type),
                        ('state', 'not in', ['Expired', 'Cancelled']),], limit=1)
                if existing_contract:
                    raise ValidationError(
                        f"The customer {record.partner_id.name} already has an active contract of type {record.order_type}."
                    )
                    return
        self.ensure_one()
        self.order_line._validate_analytic_distribution()
        lang = self.env.context.get('lang')
        mail_template = self._find_mail_template()

        if mail_template and mail_template.lang:
            lang = mail_template._render_lang(self.ids)[self.id]
        ctx = {
            'default_model': 'sale.order',
            'default_res_ids': self.ids,
            'default_template_id': mail_template.id if mail_template else None,
            'default_composition_mode': 'comment',
            'mark_so_as_sent': True,
            'default_email_layout_xmlid': 'mail.mail_notification_layout_with_responsible_signature',
            'proforma': self.env.context.get('proforma', False),
            'force_email': True,
            'model_description': self.with_context(lang=lang).type_name,
        }

        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': ctx,
        }


    def action_mark_sent(self):
        """Mark the quotation as sent without sending an email."""
        self.ensure_one()
        # Validate analytic distribution
        self.order_line._validate_analytic_distribution()
        vals = {
            'state': 'sent',  # Update state to sent
            'date_order': fields.Datetime.now(),  # Update date
        }
        self.write(vals)
        # Log a note in the chatter
        self.message_post(
            body = _("Quotation manually marked as sent."),
            subtype_id = self.env.ref('mail.mt_note').id
            )
        return True

    def action_mark_completed(self):
        """Mark the quotation as completed."""
        self.ensure_one()
        # Only allow marking as completed if the quotation is in 'sale' state
        if self.state != 'sale':
            raise UserError(_("Only Sales Orders can be marked as completed."))
        
        # Update the state to completed
        self.state = 'completed'
        
        # Log a note in the chatter
        self.message_post(
            body=_("Quotation marked as completed."),
            subtype_id=self.env.ref('mail.mt_note').id
        )
        return True

    def action_confirm(self):
        """ Confirm the given quotation(s) and set their confirmation date.

        If the corresponding setting is enabled, also locks the Sale Order.

        :return: True
        :rtype: bool
        :raise: UserError if trying to confirm cancelled SO's
        """

        if self.is_contract_quotation:
            for record in self:
                # Search for other active contracts of the same type for this customer
                existing_contract = self.env['subscription.contracts'].search([
                    ('partner_id', '=', record.partner_id.id),
                    ('contract_type', '=', record.order_type),
                    ('state', 'not in', ['Expired', 'Cancelled']),
                ], limit=1)
                if existing_contract:
                    raise ValidationError(
                        f"The customer {record.partner_id.name} already has an active contract of type {record.order_type}."
                    )
                    return

        if not all(order._can_be_confirmed() for order in self):
            raise UserError(_(
                "The following orders are not in a state requiring confirmation: %s",
                ", ".join(self.mapped('display_name')),
            ))

        self.order_line._validate_analytic_distribution()

        for order in self:
            order.validate_taxes_on_sales_order()
            if order.partner_id in order.message_partner_ids:
                continue
            order.message_subscribe([order.partner_id.id])

        self.write(self._prepare_confirmation_values())

        # Context key 'default_name' is sometimes propagated up to here.
        # We don't need it and it creates issues in the creation of linked records.
        context = self._context.copy()
        context.pop('default_name', None)

        self.with_context(context)._action_confirm()

        self.filtered(lambda so: so._should_be_locked()).action_lock()

        if self.env.context.get('send_email'):
            self._send_order_confirmation_mail()

        return True

    def action_generate_service_summary(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Generate Service Summary Report',
            'res_model': 'sale.order.summary.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_company_id': self.company_id.id or False,
            },
        }

    def generate_service_summary_report(self, start_date, end_date):
        self.ensure_one()
        if not start_date or not end_date:
            raise UserError("Start date and End date are required.")
        report_data = {
            'doc_ids': self.ids,
            'doc_model': 'sale.order',
            'docs': self,
            'start_date': start_date.strftime('%d/%b/%Y') if start_date else 'N/A',
            'end_date': end_date.strftime('%d/%b/%Y') if end_date else 'N/A',
        }
        return self.env.ref('grnlnd_task.action_service_summary_report_quotation').report_action(self, data=report_data)

class SaleOrderLocation(models.Model):
    _name = "sale.order.location"

    name = fields.Char(string="Location")


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    location = fields.Many2one('sale.order.location', 'Location')
    # location = fields.Char(string="Location")
    product_domain = fields.Binary(compute="_compute_product_domain")
    qty_min = fields.Float(string="QTY(Min)",
                           digits='Product Unit of Measure', default=1.0,
                           help='Minimum Quantity')
    service_type = fields.Selection([
        ('Required', 'Required'),
        ('Optional', 'Optional'),
    ], string='Service Type', default='Required', copy=False, tracking=True,
        help='Type of service')

    # name_ar = fields.Char(string="Product Name (Arabic)",
    #                       related="product_template_id.name_ar", store=True,
    #                       readonly=False)

    name_ar = fields.Char(
        string="Description(Arabic)",
        compute='_compute_name_ar',
        store=True, readonly=False, required=True, precompute=True)

    name = fields.Text(
        compute='_compute_name',
        store=True,
    )

    @api.depends('product_id')
    def _compute_name(self):
        """ Compute product name, slice up to the first line break, and remove data before the first ']' """
        for line in self:
            if not line.product_id:
                continue

            partner_lang = line.order_id.partner_id.lang if line.order_id.partner_id else 'en_US'
            product_lang = line.product_id.with_context(lang=partner_lang)
            name = product_lang.name or ""
            name_lines = name.splitlines()
            name = name_lines[0] if name_lines else ''

            bracket_index = name.find(']')
            if bracket_index != -1:
                name = name[bracket_index + 1:].strip()
            line.name = name

    @api.depends('product_id')
    def _compute_name_ar(self):
        """ Compute arabic product name"""
        for line in self:
            if not line.product_id:
                continue

            partner_lang = line.order_id.partner_id.lang if line.order_id.partner_id else 'en_US'
            product_lang = line.product_id.product_tmpl_id.with_context(lang=partner_lang)
            name = product_lang.name_ar or ""
            name_lines = name.splitlines()
            name = name_lines[0] if name_lines else ''

            line.name_ar = name

    # @api.constrains('name_ar')
    # def _check_name_ar(self):
    #     for record in self:
    #         if not record.name_ar:
    #             raise ValidationError(
    #                 ("The Arabic Description is missing for the product '%s'.")
    #                 % (record.product_template_id.display_name or 'Unnamed Product')
    #             )

    @api.depends('order_id')
    def _compute_product_domain(self):
        ids_list = []
        for rec in self:
            if rec.order_id:
                if rec.order_id.order_type == "Non Hazardous":
                    ids_list = [product.id for product in self.env['product.template'].search(
                        [('non_hazardous', '=', True)])]
                else:
                    ids_list = [product.id for product in self.env['product.template'].search(
                        [('hazardous', '=', True)])]
                rec.product_domain = [('id', 'in', ids_list)]
            else:
                rec.product_domain = []

class SaleOrderInvoiceWizard(models.TransientModel):
    _name = 'sale.order.invoice.wizard'
    _description = 'Contract Invoice Wizard'

    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)

    def action_generate_invoice(self):
        """Trigger the generation of an invoice."""
        active_ids = self.env.context.get('active_ids', [])
        sale_orders = self.env['sale.order'].browse(active_ids)
        for sale_order in sale_orders:
            return sale_order.action_generate_invoice(self.start_date, self.end_date)

class SaleOrderSummaryWizard(models.TransientModel):
    _name = 'sale.order.summary.wizard'
    _description = 'Quotation Service Summary Report Wizard'

    order_id = fields.Many2one('sale.order', string="Quotation", readonly=True)
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)

    def action_generate_report(self):
        self.ensure_one()
        report_action = self.order_id.generate_service_summary_report(self.start_date, self.end_date)
        report_action['type'] = 'ir.actions.report'
        return report_action


class ReportServiceSummaryQuotation(models.AbstractModel):
    _name = 'report.grnlnd_task.report_service_summary_quotation'

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data and not docids:
            raise UserError("No report data or document IDs provided.")
        order_id = data.get('doc_ids', docids[0] if docids else None)
        if not order_id:
            raise UserError("No quotation specified for report generation.")
        order = self.env['sale.order'].browse(order_id)
        if not order:
            raise UserError("No quotation found for report generation.")
        if not data or 'start_date' not in data or 'end_date' not in data:
            raise UserError("Please specify start and end dates via the wizard.")
        start_date = data['start_date']
        end_date = data['end_date']

        # Find invoices (account.move) related to this sale order
        invoices = self.env['account.move'].search([
            ('invoice_origin', '=', order.name),  # Invoice origin matches sale order name
            ('move_type', 'in', ['out_invoice', 'out_refund'])  # Only customer invoices
        ])

        # If no invoices found by origin, try other relationships
        if not invoices:
            invoices = order.invoice_ids  # Direct relationship if it exists

        service_dict = {}

        # For each invoice, use EXACTLY the same logic as account_move.py
        for invoice in invoices:
            # This is the EXACT same line as account_move.py
            tasks = self.env['project.task'].search([('invoice_id', '=', invoice.id)])

            # This is the EXACT same logic as account_move.py
            for task in tasks:
                for service_line in task.contract_service_ids:
                    product = service_line.name
                    if not product:
                        continue
                    product_id = product.id
                    service_name = product.name

                    if product_id not in service_dict:
                        service_dict[product_id] = {
                            'service_name': service_name,
                            'entries': [],
                            'total_qty': 0.0,
                        }

                    service_dict[product_id]['entries'].append({
                        'service_ticket_date': task.date_deadline if task.date_deadline else '',
                        'service_ticket_number': task.service_ticket_number or 'N/A',
                        'driver_name': task.driver_id.name if task.driver_id else 'N/A',
                        'vehicle_number': task.vehicle_number.name if task.vehicle_number else 'N/A',
                        'service_qty': service_line.quantity or 0.0,
                        'location': service_line.location.name if service_line.location.name else '-',
                    })

                    service_dict[product_id]['total_qty'] += service_line.quantity or 0.0

        # Convert to format for template (flattened since your template expects simple structure)
        service_data = []
        for product_id, product_info in service_dict.items():
            # For quotation report, aggregate the data
            total_qty = product_info['total_qty']
            first_entry = product_info['entries'][0] if product_info['entries'] else {}

            service_data.append({
                'service_name': product_info['service_name'],
                'location': first_entry.get('location', '-'),
                'qty': total_qty,
                'driver_name': first_entry.get('driver_name', 'N/A'),
                'vehicle_number': first_entry.get('vehicle_number', 'N/A'),
            })

        # If no data found from invoices/tasks, fall back to order lines
        if not service_data:
            for line in order.order_line:
                service_data.append({
                    'service_name': line.name,
                    'location': line.location.name if hasattr(line, 'location') and line.location else '-',
                    'qty': line.product_uom_qty,
                    'driver_name': 'N/A',
                    'vehicle_number': 'N/A',
                })

        return {
            'doc_model': 'sale.order',
            'doc_ids': [order.id],
            'doc': order,
            'start_date': start_date,
            'end_date': end_date,
            'services': service_data,
        }
from odoo import models, fields, api
class SaleOrder(models.Model):
    _inherit = 'sale.order'
    # The field definition
    sales_threshold = fields.Selection([
        ('silver', 'Silver'),
        ('gold', 'Gold'),
        ('platinum', 'Platinum')
    ], string="Sales Threshold", compute="_compute_sales_threshold")  # Removed store=True
    # THIS MUST BE INDENTED (4 spaces or 1 tab)
    @api.depends('amount_total')
    def _compute_sales_threshold(self):
        params = self.env['ir.config_parameter'].sudo()

        # Pulling the dynamic limits from your settings
        silver_limit = float(params.get_param('grnlnd.silver_threshold', 0.0))
        gold_limit = float(params.get_param('grnlnd.gold_threshold', 0.0))

        for order in self:
            if order.amount_total <= silver_limit:
                order.sales_threshold = 'silver'
            elif order.amount_total <= gold_limit:
                order.sales_threshold = 'gold'
            else:
                order.sales_threshold = 'platinum'