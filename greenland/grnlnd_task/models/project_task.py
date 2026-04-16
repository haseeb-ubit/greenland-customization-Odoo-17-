from email.policy import default


from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError, AccessError
from odoo.tools import date_utils
from collections import defaultdict
from datetime import datetime, timedelta
from odoo.exceptions import UserError
from datetime import date
from operator import itemgetter
import logging

_logger = logging.getLogger(__name__)

CLOSED_STATES = {
    '1_done': 'Done',
    '1_canceled': 'Canceled',
}

class DisposalFacilitator(models.Model):
    _name = "disposal.facilitator"

    name = fields.Char()

class Vehicle(models.Model):
    _name = "vehicle"

    name = fields.Char("Vehicle Plate Number")

class Driver(models.Model):
    _name = "driver"

    name = fields.Char("Driver")

class Container(models.Model):
    _name = "container"

    name = fields.Char("Container Name")

class CustomerSignature(models.Model):
    _name = 'customer.signature'
    _description = 'Customer Signature'

    contract_customer_id = fields.Many2one(
        comodel_name='res.partner',
        string="Customer",
        required=False, change_default=True, index=True,
        tracking=1,
        check_company=True,
        domain=lambda self: [('is_company', '=', True)]
    )
    signature = fields.Binary(string='Signature', attachment=True)
    name = fields.Char(string='Signature Name', compute='_compute_name')
    receiver_name = fields.Char(string='Receiver Name', required=True)
    receiver_position = fields.Char(string='Receiver Position')

    @api.depends('contract_customer_id')
    def _compute_name(self):
        for record in self:
            record.name = f"Signature of {record.contract_customer_id.name}" if record.contract_customer_id else ''


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not args:
            args = []
        domain = ['|', '|', ('name', operator, name), ('customer_id', operator, name), ('ref', operator, name)]
        partners = self.search(domain + args, limit=limit)
        return partners.name_get()


class ProjectTask(models.Model):
    _inherit = 'project.task'
    _rec_name = 'service_ticket_number'

    is_todo_task = fields.Boolean(
        string="is todo task",
        default=False,
        store=True
    )
    ticket_type = fields.Selection([
        ('digital', 'Digital'),
        ('manual', 'Manual'),
    ], string='Ticket Type', default='manual', required=True)
    name = fields.Char(string='Name', required=False)
    service_ticket_number = fields.Char(string='Service Ticket Number', readonly="ticket_type == 'digital'")
    contract_customer_id = fields.Many2one(
        comodel_name='res.partner',
        string="Customer",
        required=False, change_default=True, index=True,
        tracking=1,
        check_company=True,
        domain=lambda self: [('is_company', '=', True)]
    )
    sale_contract_id = fields.Many2one("subscription.contracts", "Contract")
    contract_service_ids = fields.One2many('project.task.services.line', 'contract_service_id', 'Services')
    #driver = fields.Many2one("driver", "Driver")
    driver_id = fields.Many2one("hr.employee", string="Driver",
                                domain="[('job_id.name', '=', 'Driver')]"
                                )
    signature_id = fields.Many2one('customer.signature', string='Customer Signature',
                                   domain="[('contract_customer_id', '=', contract_customer_id)]")
    signature_image = fields.Binary(string='Signature Image', compute='_compute_signature_image', store=False)
    vehicle_number = fields.Many2one("vehicle", "Vehicle Plate No.")
    disposal_facility_delivery_note = fields.Char("Disposal Facility Delivery Note")
    disposal_facility_name = fields.Many2one('disposal.facilitator', 'Disposal Facility Name')
    contract_type = fields.Selection([
        ('Non Hazardous', 'Non Hazardous'),
        ('Hazardous', 'Hazardous'),
    ],
        default='Non Hazardous',
        # related='sale_contract_id.contract_type',
        string="Contract Type",
        store=True,
        readonly=True,
    )
    disposal_date = fields.Date("Disposal Date")
    date_deadline = fields.Date(string='Service Ticket Date', index=True, tracking=True)
    invoice_id = fields.Many2one("account.move", "Invoice")
    state = fields.Selection([
        ('01_in_progress', 'In Progress'),
        ('02_changes_requested', 'Changes Requested'),
        ('03_approved', 'Approved'),
        *CLOSED_STATES.items(),
        ('04_waiting_normal', 'Waiting'),
        ('05_invoiced', 'Invoiced'),
        ('06_cancelled', 'Cancelled'),
        ('07_before_invoiced', 'BeforeInvoiced')
    ], string='State', copy=False, default='01_in_progress', required=True, compute='_compute_state',
        inverse='_inverse_state', readonly=False, store=True, index=True, recursive=True, tracking=True)

    # Driver-only state field with exactly 2 options
    driver_status = fields.Selection([
        ('01_in_progress', 'In Progress'),
        ('1_done', 'Done'),
    ], string='Status', compute='_compute_driver_status', inverse='_inverse_driver_status', store=True)

    @api.depends('state')
    def _compute_driver_status(self):
        """Compute driver status from main state"""
        for record in self:
            if record.state == '01_in_progress':
                record.driver_status = '01_in_progress'
            elif record.state == '07_before_invoiced':
                # Treat BeforeInvoiced as Done for drivers
                record.driver_status = '1_done'
            else:
                # Any other state shows as Done for drivers
                record.driver_status = '1_done'

    def _inverse_driver_status(self):
        """Update main state when driver changes driver_status"""
        for record in self:
            if record.driver_status == '01_in_progress':
                # If driver sets to In Progress, set the actual state to In Progress
                record.state = '01_in_progress'
            elif record.driver_status == '1_done':
                # If driver sets to Done, preserve the original state if it was BeforeInvoiced
                # Otherwise set to a done state (like Invoiced)
                if record.state == '07_before_invoiced':
                    # Keep it as BeforeInvoiced
                    pass
                else:
                    # Set to Invoiced as a default done state
                    record.state = '05_invoiced'

    invoice_state = fields.Selection(
        string="Invoice State",
        selection=[
            ('draft', 'Draft Invoice'),
            ('posted', 'Invoice Confirmed'),
            ('cancel', 'Cancelled'),
            ('not', 'Not Invoiced'),
        ],
        compute='_compute_invoice_state',
        store=True,
        default='not'
    )
    customer_id = fields.Char(related='contract_customer_id.customer_id', string="Customer ID", readonly=True,
                              store=True)
    ref = fields.Char(related='contract_customer_id.ref', string="Filing Reference", readonly=True, store=True)
    task_sale_order_id = fields.Many2one('sale.order', string='Sales Order',
                                         help="Sales order to which the project is linked.")
    lock = fields.Boolean(string='Lock', default=False,
                          help='Lock subscription contract so that further'
                               ' modifications are not possible.')
    is_readonly = fields.Boolean(string="Is Readonly", compute="_compute_is_readonly", store=True)

    is_manual_ticket = fields.Boolean(string="Is Manual Ticket", compute="_compute_is_manual_ticket")

    # Add this field for Odoo 17 group-based readonly logic
    is_driver_user = fields.Boolean(
        string="Is Driver User",
        compute='_compute_is_driver_user',
        store=False
    )

    container_in = fields.Many2one('container', string='Container In', required=False)
    container_out = fields.Many2one('container', string='Container Out', required=False)

    is_done_readonly = fields.Boolean(
        string="Is Done Readonly",
        compute="_compute_is_done_readonly",
        store=False
    )

    # Computed fields for list view display
    first_location = fields.Char(
        string="Location",
        compute="_compute_first_location_service",
        store=True
    )
    
    first_service = fields.Char(
        string="Services",
        compute="_compute_first_location_service",
        store=True
    )
    invoice_display = fields.Char(
        string="Invoice",
        compute="_compute_invoice_display",
        store=False
    )

    @api.depends("invoice_id", "invoice_state")
    def _compute_invoice_display(self):
        for task in self:
            # Only display invoice number if invoice exists and state is 'posted' or 'draft'
            # Hide invoice number for cancelled invoices (invoice_state = 'not')
            if task.invoice_id and task.invoice_state in ('draft', 'posted'):
                task.invoice_display = task.invoice_id.name
            else:
                task.invoice_display = False

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        user = self.env.user
        if user.has_group('grnlnd_task.group_driver_access') or user.has_group('grnlnd_task.group_dispatcher_access'):
            res['ticket_type'] = 'digital'
        return res

    @api.depends('ticket_type')
    def _compute_is_manual_ticket(self):
        for rec in self:
            rec.is_manual_ticket = rec.ticket_type == 'manual'

    @api.depends('signature_id')
    def _compute_signature_image(self):
        for record in self:
            record.signature_image = record.signature_id.signature if record.signature_id else False

    def action_collect_signature(self):
        self.ensure_one()
        if not self.contract_customer_id:
            raise ValidationError(_("Please assign a customer before collecting a signature."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Collect Customer Signature'),
            'res_model': 'customer.signature.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_task_id': self.id,
                'default_contract_customer_id': self.contract_customer_id.id,
            },
        }

    def unlink(self):
        driver_group = self.env.ref('grnlnd_task.group_driver_access')
        if driver_group in self.env.user.groups_id:
            raise UserError(_("Drivers are not allowed to delete service tickets."))
        return super(ProjectTask, self).unlink()
    def action_preview_job(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': '/report/pdf/grnlnd_task.action_report_service_ticket/%s' % self.id,
        }

    @api.constrains('state', 'signature_id', 'date_deadline', 'ticket_type')
    def _check_signature_and_date_before_done(self):
        for record in self:
            if record.state == '1_done' and record.ticket_type == 'digital' and not record.is_todo_task:
                if not record.signature_id:
                    raise ValidationError(
                        _("A customer signature is required before marking a Digital Service Ticket as Done."))
                if not record.date_deadline:
                    raise ValidationError(
                        _("A service date is required before marking a Digital Service Ticket as Done."))

    @api.depends('invoice_id', 'invoice_id.state', 'invoice_id.reversal_move_id')
    def _compute_invoice_state(self):
        # Collect invoice IDs safely using .id (which always returns int or False for Many2one)
        invoice_ids = set()
        for task in self:
            inv_id = task.invoice_id.id if task.invoice_id else False
            if inv_id:
                invoice_ids.add(inv_id)
        
        # Pre-fetch all invoices at once and read their states directly
        invoice_data = {}
        if invoice_ids:
            invoices = self.env['account.move'].browse(list(invoice_ids))
            # Use read() to get data without triggering singleton errors
            invoice_reads = invoices.read(['id', 'state', 'reversal_move_id'])
            for inv_read in invoice_reads:
                reversal_move_id = False
                if inv_read.get('reversal_move_id'):
                    # Many2one fields in read() return tuple (id, name) or just id
                    rev_move = inv_read['reversal_move_id']
                    if isinstance(rev_move, (list, tuple)) and len(rev_move) > 0:
                        reversal_move_id = rev_move[0]
                    elif isinstance(rev_move, int):
                        reversal_move_id = rev_move
                
                invoice_data[inv_read['id']] = {
                    'state': inv_read.get('state', 'draft'),
                    'reversal_move_id': reversal_move_id
                }
        
        # Pre-fetch reversal moves if needed
        reversal_move_ids = [data['reversal_move_id'] for data in invoice_data.values() if data['reversal_move_id']]
        reversal_moves = {}
        if reversal_move_ids:
            rev_reads = self.env['account.move'].browse(reversal_move_ids).read(['id', 'state'])
            reversal_moves = {rev['id']: rev.get('state', 'draft') for rev in rev_reads}
        
        for task in self:
            # Get invoice ID using .id property (safe for Many2one)
            invoice_id = task.invoice_id.id if task.invoice_id else False
            if not invoice_id:
                task.invoice_state = 'not'
                continue
            
            # Get invoice data from pre-fetched data
            inv_data = invoice_data.get(invoice_id)
            if not inv_data:
                task.invoice_state = 'not'
                continue
            
            invoice_state = inv_data.get('state', 'draft')
            
            if invoice_state == 'draft':
                task.invoice_state = 'draft'
            elif invoice_state == 'posted':
                # Check if invoice has been reversed
                reversal_move_id = inv_data.get('reversal_move_id')
                if reversal_move_id and reversal_move_id in reversal_moves:
                    reversal_state = reversal_moves[reversal_move_id] or 'draft'
                    if reversal_state == 'posted':
                        task.invoice_state = 'not'
                    else:
                        task.invoice_state = 'posted'
                else:
                    task.invoice_state = 'posted'
            elif invoice_state == 'cancel':
                # When invoice is cancelled, set invoice_state to 'not' to allow creating new invoice
                task.invoice_state = 'not'
            else:
                task.invoice_state = 'not'

    @api.depends('invoice_state')
    def _compute_is_readonly(self):
        for record in self:
            record.is_readonly = record.invoice_state == 'posted'
            if record.invoice_state == 'posted':
                self.lock = True

    @api.constrains('contract_service_ids')
    def _check_contract_service_ids(self):
        if self.is_todo_task == False:
            for record in self:
                if record.contract_type == 'Non Hazardous':
                    if len(record.contract_service_ids) > 1:
                        raise ValidationError('For Non Hazardous Waste Service Ticket: Not more than 1 Service item')
                if len(record.contract_service_ids) < 1:
                    raise ValidationError("Please add a Service item before proceeding.")
                for line in record.contract_service_ids:
                    if not line.location:
                        raise ValidationError("Each Service item must have a Location.")
                    if not line.product_uom_id:
                        raise ValidationError("Each Service item must have a Unit of Measure.")

    def merge_duplicate_product_lines(self, res):
        for line in res.contract_service_ids:
            if line.id in res.contract_service_ids.ids:
                line_ids = res.contract_service_ids.filtered(lambda m: m.name.id == line.name.id)
                line_ids[0].quantity = sum(line_ids.mapped('quantity'))
                line_ids[1:].unlink()

    @api.constrains('service_ticket_number', 'is_todo_task', 'ticket_type')
    def _check_service_ticket_number_unique(self):
        for record in self:
            if not record.is_todo_task and record.service_ticket_number:
                duplicates = self.env['project.task'].search([
                    ('service_ticket_number', '=', record.service_ticket_number),
                    ('is_todo_task', '=', False),
                    ('id', '!=', record.id),
                ])
                if duplicates:
                    raise ValidationError(_("This Service Ticket No. already assigned!"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'is_todo_task' not in vals:
                vals['is_todo_task'] = self._context.get('default_is_todo_task', False)

        if any(not vals.get('is_todo_task', False) for vals in vals_list):
            for vals in vals_list:
                if not vals.get('is_todo_task', False) and vals.get('ticket_type') == 'manual':
                    vals["state"] = "1_done"
                if not vals.get('is_todo_task', False) and vals.get('ticket_type') == 'digital':
                    sequence = self.env['ir.sequence'].next_by_code('digital.service.ticket')
                    vals['service_ticket_number'] = sequence
                    vals['date_deadline'] = False
            res = super().create(vals_list)
            for data in vals_list:
                if 'sale_contract_id' in data and data['sale_contract_id']:
                    task_count = self.env['subscription.contracts'].search([
                        ('id', '=', data['sale_contract_id'])])
                    task_count._compute_task_count()
            self.merge_duplicate_product_lines(res)
            return res
        return super().create(vals_list)

    @api.onchange('contract_customer_id')
    def _onchange_contract_customer_id_field(self):
        if self.contract_customer_id and self.sale_contract_id and self.sale_contract_id.partner_id != self.contract_customer_id:
            self.sale_contract_id = None
        # set related field values
        self.contract_type = self.env.context.get('default_contract_type')
        # Clear One2many field
        self.contract_service_ids = [(5, 0, 0)]  # Removes all records

    def action_view_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoices',
            'view_mode': 'tree,form',
            'res_model': 'account.move',
            'domain': [('id', '=', self.invoice_id.id)],
        }

    def write(self, vals):
        # DRIVER RESTRICTION: Prevent drivers from changing Done status AND restrict to allowed states
        if 'state' in vals or 'driver_status' in vals:
            # Check if user is a driver (and not an admin)
            if self.env.user.has_group('grnlnd_task.group_driver_access') and not self.env.user.has_group(
                    'base.group_system'):
                # If driver_status is being changed, validate it
                if 'driver_status' in vals:
                    allowed_states = ['01_in_progress', '1_done']
                    if vals['driver_status'] not in allowed_states:
                        raise UserError("Drivers can only set status from 'In Progress' to 'Done'.")

                # If state is being changed directly, validate it (backup check)
                if 'state' in vals:
                    allowed_states = ['01_in_progress', '1_done']
                    if vals['state'] not in allowed_states:
                        raise UserError("Drivers can only set from status 'In Progress' to 'Done'.")

                for record in self:
                    # Prevent drivers from changing state if it's already Done
                    if record.state == '1_done' and (
                            ('driver_status' in vals and vals['driver_status'] != '1_done') or
                            ('state' in vals and vals['state'] != '1_done')
                    ):
                        raise UserError(
                            "You cannot change the status once it's marked as 'Done'. Please contact your administrator if needed.")

        # Call the parent write method first
        result = super(ProjectTask, self).write(vals)

        # Your existing write logic - iterate through each record
        for record in self:
            if record.is_todo_task == False:  # Now checking on individual record
                if 'sale_contract_id' in vals:
                    task_count = self.env['subscription.contracts'].search([
                        ('id', '=', vals['sale_contract_id'])])
                    task_count._compute_task_count()
                record.merge_duplicate_product_lines(record)  # Pass individual record

        # Validation logic - iterate through each record
        if not self._context.get('bypass_service_validation'):
            for record in self:
                if not record.is_todo_task:  # Check on individual record
                    if len(record.contract_service_ids) < 1:
                        raise ValidationError("Please add a Service item before proceeding.")
                    for line in record.contract_service_ids:
                        if not line.location:
                            raise ValidationError("Each Service item must have a Location.")
                        if not line.product_uom_id:
                            raise ValidationError("Each Service item must have a Unit of Measure.")

        return result

    def _compute_is_driver_user(self):
        for rec in self:
            rec.is_driver_user = self.env.user.has_group('grnlnd_task.group_driver_access')


    @api.depends('state')
    def _compute_is_done_readonly(self):
        user = self.env.user
        for rec in self:
            rec.is_done_readonly = rec.state == '1_done' and user.has_group('grnlnd_task.group_driver_access')

    @api.depends('contract_service_ids', 'contract_service_ids.location', 'contract_service_ids.name')
    def _compute_first_location_service(self):
        for rec in self:
            if rec.contract_service_ids:
                # Get the first service line
                first_line = rec.contract_service_ids[0]
                rec.first_location = first_line.location.name if first_line.location else ''
                rec.first_service = first_line.name.name if first_line.name else ''
            else:
                rec.first_location = ''
                rec.first_service = ''

    def action_mark_done(self):
        self.ensure_one()
        # Set state to '1_done' and trigger constraints
        self.state = '1_done'
        return True

    def action_mark_in_progress(self):
        self.ensure_one()
        # Set state to '01_in_progress' and trigger constraints
        self.state = '01_in_progress'
        return True

    def _get_contract_price_and_uom_for_product(self, customer_id, product_id, location_id=None, service_ticket=None):
        """Get the contract price and UOM for a specific customer and product"""
        customer = self.env['res.partner'].browse(customer_id)
        
        # First, if service ticket is linked to a specific contract, use that contract
        if service_ticket and service_ticket.sale_contract_id:
            contract = service_ticket.sale_contract_id
            
            # Find the contract line for this product and location
            contract_line = contract.contract_line_ids.filtered(
                lambda line: line.product_id.id == product_id and 
                (not location_id or line.location.id == location_id)
            )
            if contract_line:
                return contract_line[0].price_unit, contract_line[0].product_uom_id.id
            else:
                
                # If no exact location match, try to find any line with matching product (ignore location)
                fallback_line = contract.contract_line_ids.filtered(lambda line: line.product_id.id == product_id)
                if fallback_line:
                    return fallback_line[0].price_unit, fallback_line[0].product_uom_id.id
        
        # If service ticket is linked to a sale order, use that sale order
        if service_ticket and service_ticket.task_sale_order_id:
            sale_order = service_ticket.task_sale_order_id
            # Find the order line for this product and location
            order_line = sale_order.order_line.filtered(
                lambda line: line.product_id.id == product_id and 
                (not location_id or line.location.id == location_id)
            )
            if order_line:
                return order_line[0].price_unit, order_line[0].product_uom.id
        
        # Fallback: search for any active contract for this customer
        subscription_contract = self.env['subscription.contracts'].search([
            ('partner_id', '=', customer_id),
            ('state', 'not in', ['Expired', 'Cancelled']),
            ('contract_line_ids.product_id', '=', product_id)
        ], limit=1)
        
        if subscription_contract:
            # Find the contract line for this product and location
            contract_line = subscription_contract.contract_line_ids.filtered(
                lambda line: line.product_id.id == product_id and 
                (not location_id or line.location.id == location_id)
            )
            if contract_line:
                return contract_line[0].price_unit, contract_line[0].product_uom_id.id
            else:
                # If no exact location match, try to find any line with matching product (ignore location)
                fallback_line = subscription_contract.contract_line_ids.filtered(lambda line: line.product_id.id == product_id)
                if fallback_line:
                    return fallback_line[0].price_unit, fallback_line[0].product_uom_id.id
        
        # If not found in subscription contracts, try sale orders
        sale_order = self.env['sale.order'].search([
            ('partner_id', '=', customer_id),
            ('state', 'in', ['sale', 'done']),
            ('order_line.product_id', '=', product_id)
        ], limit=1)
        
        if sale_order:
            # Find the order line for this product and location
            order_line = sale_order.order_line.filtered(
                lambda line: line.product_id.id == product_id and 
                (not location_id or line.location.id == location_id)
            )
            if order_line:
                return order_line[0].price_unit, order_line[0].product_uom.id
        
        # Fallback to product list price and UOM if no contract price found
        product = self.env['product.product'].browse(product_id)
        return product.list_price, product.uom_id.id

    def action_open_link_invoice_wizard(self):
        """Action to validate and open the Link Invoice Wizard"""
        if not self:
            raise UserError(_("No tickets selected."))

        # 1. Check consistency of Customer
        customers = self.mapped('contract_customer_id')
        if len(customers) > 1:
            raise UserError(_("You have selected tickets from multiple customers. Please select tickets from a single customer to link."))
        if not customers:
             raise UserError(_("The selected tickets do not have a customer assigned."))

        # 2. Safety net in case JS fails: block only tickets linked to a confirmed invoice
        posted = self.filtered(lambda t: t.invoice_state == 'posted')
        if posted:
            raise UserError(_(
                "The following tickets are already linked to a confirmed invoice "
                "and cannot be re-linked:\n%s"
            ) % ', '.join(posted.mapped('service_ticket_number')))

        # 3. Return Action
        return {
            'type': 'ir.actions.act_window',
            'name': _('Link to Existing Invoice'),
            'res_model': 'link.invoice.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_ids': self.ids, 
                'default_partner_id': customers[0].id
            },
        }

    def _handle_invoice_reversal(self):
        """Called when the linked invoice is reversed. Clears invoice_id and resets state."""
        # Filter to only tickets that actually have an invoice linked
        tasks_to_reset = self.filtered(lambda t: t.invoice_id)
        if not tasks_to_reset:
            return
        
        tasks_to_reset.with_context(bypass_service_validation=True).write({
            'invoice_id': False,
            'state': '03_approved'
        })

    def action_generate_service_invoice(self):
        """Generate invoice for selected service tickets"""
        # Check if all selected tickets belong to the same customer
        customers = self.mapped('contract_customer_id')
        if len(customers) > 1:
            raise UserError(_('Cannot generate invoice for tickets from multiple customers. Please select tickets from a single customer.'))

        # Group tickets by customer
        tickets_by_customer = {}
        for ticket in self:
            # Check invoice_state instead of state - allow creating new invoice if invoice_state is 'not' (cancelled or not invoiced)
            if ticket.invoice_state == 'posted':
                raise UserError(_('Ticket %s is already invoiced (Invoice: %s).') % (ticket.service_ticket_number, ticket.invoice_id.name if ticket.invoice_id else ''))
            if not ticket.contract_customer_id:
                raise UserError(_('Ticket %s has no customer assigned.') % ticket.service_ticket_number)

            customer_id = ticket.contract_customer_id.id
            if customer_id not in tickets_by_customer:
                tickets_by_customer[customer_id] = []
            tickets_by_customer[customer_id].append(ticket)

        # Create invoice for each customer's tickets
        for customer_id, tickets in tickets_by_customer.items():
            customer = self.env['res.partner'].browse(customer_id)

            # Prepare invoice lines
            invoice_line_vals = []
            # Aggregate by (product, location) to avoid duplicates
            aggregated = {}
            for ticket in tickets:
                for service in ticket.contract_service_ids:
                    # Get contract price and UOM instead of product list price and UOM
                    contract_price, contract_uom_id = self._get_contract_price_and_uom_for_product(
                        customer_id, 
                        service.name.id, 
                        service.location.id if service.location else None,
                        ticket  # Pass the service ticket to use its linked contract
                    )
                    key = (service.name.id, service.location.id if service.location else None)
                    if key not in aggregated:
                        aggregated[key] = {
                            'product_id': service.name.id,
                            'name': service.name.name,
                            'name_ar': service.name.product_tmpl_id.name_ar,
                            'quantity': 0.0,
                            'total_amount': 0.0,
                            'product_uom_id': contract_uom_id,
                            'tax_ids': list(service.name.taxes_id.ids),
                            'location': service.location.id if service.location else None,
                            'line_description': f"{service.name.name} - {service.location.name if service.location else ''}"
                        }
                    aggregated_line = aggregated[key]
                    aggregated_line['quantity'] += service.quantity or 0.0
                    aggregated_line['total_amount'] += (contract_price or 0.0) * (service.quantity or 0.0)

            # Build final invoice lines with averaged unit price to preserve totals
            for data in aggregated.values():
                quantity = data['quantity'] or 0.0
                unit_price = data['total_amount'] / quantity if quantity else 0.0
                invoice_line_vals.append((0, 0, {
                    'product_id': data['product_id'],
                    'name': data['name'],
                    'name_ar': data['name_ar'],
                    'quantity': quantity,
                    'price_unit': unit_price,
                    'product_uom_id': data['product_uom_id'],
                    'tax_ids': [(6, 0, data['tax_ids'])],
                    'location': data['location'],
                    'line_description': data['line_description']
                }))

            if not invoice_line_vals:
                raise UserError(_('No services found in the selected tickets for customer %s.') % customer.name)

            # Create invoice
            invoice = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': customer_id,
                'invoice_date': fields.Date.today(),
                'invoice_line_ids': invoice_line_vals,
                'invoice_payment_term_id': customer.property_payment_term_id.id,
                'is_service_ticket_invoice': True,
            })

            # Update tickets with invoice reference and state
            for ticket in tickets:
                ticket.write({
                    'invoice_id': invoice.id,
                    'state': '05_invoiced'
                })

            # Return the created invoice in form view
            action = {
                'type': 'ir.actions.act_window',
                'name': _('Generated Invoice'),
                'res_model': 'account.move',
                'res_id': invoice.id,
                'view_mode': 'form',
                'target': 'current',
                'context': {'form_view_initial_mode': 'edit'},
            }

            # Get the form view for invoices
            form_view = self.env.ref('account.view_move_form')
            if form_view:
                action['views'] = [(form_view.id, 'form')]

            return action

class ProjectTaskServiceLine(models.Model):
    _name = "project.task.services.line"

    name = fields.Many2one("product.product", "Services")
    location = fields.Many2one('sale.order.location', 'Location', domain="[('id', 'in', available_location_ids)]")
    available_location_ids = fields.Many2many('sale.order.location', compute='_compute_available_locations', store=True)
    # location_domain = fields.Binary(compute="_compute_location_domain")
    quantity = fields.Float("QTY", default=1.0)
    contract_service_id = fields.Many2one("project.task", "Service Ticket ID")
    product_domain = fields.Binary(compute="_compute_product_domain")
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure',
                                     compute='_compute_product_uom', store=True,
                                     help='Unit of measure of product')
    is_qty_editable = fields.Boolean(compute='_compute_product_uom', store=True,)
    contract_type = fields.Selection(
        related='contract_service_id.contract_type',
        string="Contract Type",
        store=True,
        readonly=True,
    )
    lock = fields.Boolean(string='Lock', default=False,
                          help='Lock subscription contract so that further'
                               ' modifications are not possible.')

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
    is_readonly = fields.Boolean(string="Is Readonly", compute="_compute_is_readonly", store=True)

    is_driver_user = fields.Boolean(
        related='contract_service_id.is_driver_user',
        string="Is Driver User",
        store=False,
        readonly=True,
    )

    @api.depends('name', 'contract_service_id', 'contract_service_id.task_sale_order_id')
    def _compute_available_locations(self):
        for record in self:
            location_ids = []
            if record.contract_service_id and record.contract_service_id.task_sale_order_id and record.name:
                # Get locations from sale order lines for this product
                sale_order = record.contract_service_id.task_sale_order_id
                matching_lines = sale_order.order_line.filtered(
                    lambda line: line.product_id.id == record.name.id
                )
                location_ids.extend(matching_lines.mapped('location').ids)

            elif record.contract_service_id and record.contract_service_id.sale_contract_id and record.name:
                subscription_contract = record.contract_service_id.sale_contract_id
                matching_lines = subscription_contract.contract_line_ids.filtered(
                    lambda line: line.product_id.id == record.name.id
                )
                location_ids.extend(matching_lines.mapped('location').ids)

            record.available_location_ids = list(set(location_ids))

    @api.onchange('name')
    def _onchange_name(self):
        """Clear location when product changes to ensure valid selection"""
        self.location = False


    @api.depends('contract_service_id.invoice_state')
    def _compute_invoice_state(self):
        for task_line in self:
            task_line.invoice_state = 'not'
            if task_line.contract_service_id:
                # Map the states from account.move to custom labels
                if task_line.contract_service_id.invoice_state == 'draft':
                    task_line.invoice_state = 'draft'
                elif task_line.contract_service_id.invoice_state == 'posted':
                    task_line.invoice_state = 'posted'
                elif task_line.contract_service_id.invoice_state == 'cancel':
                    task_line.invoice_state = 'cancel'
            else:
                task_line.invoice_state = 'not'

    @api.depends('invoice_state')
    def _compute_is_readonly(self):
        for record in self:
            record.is_readonly = record.invoice_state == 'posted'



    # @api.depends('contract_service_id')
    # def _compute_location_domain(self):
    #     location_ids_list = []
    #     for rec in self:
    #         if rec.contract_service_id:
    #             for lines in rec.contract_service_id.sale_contract_id.contract_line_ids:
    #                 location_ids_list.append(lines.location.name)
    #             for sales_line in rec.contract_service_id.task_sale_order_id.order_line:
    #                 location_ids_list.append(sales_line.location.name)
    #                 rec.location_domain = [location_ids_list]
    #         else:
    #             rec.location_domain = None

    @api.depends('contract_service_id')
    def _compute_product_domain(self):
        ids_list = []
        for rec in self:
            if rec.contract_service_id:
                # if rec.contract_service_id.contract_type == "Non Hazardous":
                for lines in rec.contract_service_id.sale_contract_id.contract_line_ids:
                    ids_list.append(lines.product_id.id)
                for sales_line in rec.contract_service_id.task_sale_order_id.order_line:
                    ids_list.append(sales_line.product_id.id)
                rec.product_domain = [('id', 'in', ids_list)]
                # else:
                #     rec.product_domain = []
            else:
                rec.product_domain = None

    @api.depends('name', 'contract_service_id', 'location')
    def _compute_product_uom(self):
        """ Compute product uom """
        for rec in self:
            rec.product_uom_id = False  # Default empty

            # Ensure a contract and product are selected
            if rec.contract_service_id and rec.name and rec.location:
                contract = rec.contract_service_id.sale_contract_id
                task_sale= rec.contract_service_id.task_sale_order_id
                if contract:
                    # Get the contract line for the selected product and location
                    contract_line = contract.contract_line_ids.filtered(
                        lambda line: line.product_id.id == rec.name.id and line.location.id == rec.location.id
                    )
                    if contract_line:
                        rec.product_uom_id = contract_line[0].product_uom_id.id
                    else:
                        rec.product_uom_id = rec.name.uom_id.id  # Fallback to product's UoM
                elif task_sale:
                    task_line = task_sale.order_line.filtered(
                        lambda line: line.product_id.id == rec.name.id and line.location.id == rec.location.id
                    )
                    if task_line:
                        rec.product_uom_id = task_line[0].product_uom.id
                    else:
                        rec.product_uom_id = rec.name.uom_id.id

            if rec.contract_service_id.contract_type == "Non Hazardous":
                if rec.name.uom_id.name == "Hourly" or rec.name.uom_id.name == "Hours":
                    rec.is_qty_editable = True
                else:
                    rec.is_qty_editable = False
            else:
                rec.is_qty_editable = True


class ContractSubscription(models.Model):
    _inherit = 'subscription.contracts'

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string="Customer",
        required=True, change_default=True, index=True,
        domain=lambda self: [('is_company', '=', True)]
    )

    @api.model
    def write(self, vals):
        # Check if products are already added before allowing the change of contract type
        if 'contract_type' in vals and self.contract_line_ids:
            raise ValidationError("The contract type cannot be changed if the products are already added.")
        
        
        if 'state' in vals and vals['state'] == 'Ongoing' and not self.lock:
            vals['lock'] = True
            
        return super(ContractSubscription, self).write(vals)

    ticket_task_count = fields.Integer(store=True,
                                       compute='_compute_task_count',
                                       string='Task count',
                                       help='Number of task tickets generated')
    contract_type = fields.Selection([
        ('Non Hazardous', 'Non Hazardous'),
        ('Hazardous', 'Hazardous'),
    ], string='Contract Type', default='Non Hazardous', copy=False, tracking=True,
        help='Type of subscription contract')
    payment_terms_id = fields.Many2one("account.payment.term", "Payment terms")
    customer_po = fields.Char("Customer PO")

    @api.constrains('partner_id', 'contract_type', 'state')
    def _check_unique_active_contract(self):
        """
        Ensure a customer has only one active contract of each type.
        """
        for record in self:
            # if record.state == 'active':
            # Search for other active contracts of the same type for this customer
            existing_contract = self.search([
                ('id', '!=', record.id),  # Exclude current record
                ('partner_id', '=', record.partner_id.id),
                ('contract_type', '=', record.contract_type),
                ('state', 'not in', ['Expired','Cancelled']),
            ], limit=1)
            if existing_contract:
                raise ValidationError(
                    f"The customer {record.partner_id.name} already has an active contract of type {record.contract_type}."
                )

    @api.onchange('contract_type')
    def _onchange_contract_type_field(self):
        if self.contract_type:
            # Clear One2many contract_line_ids field
            self.contract_line_ids = [(5, 0, 0)]  # Removes all records

    @api.depends('partner_id')
    def _compute_task_count(self):
        for record in self:
            record.ticket_task_count = self.env['project.task'].search_count([
                ('sale_contract_id', '=', record.id)])

    def action_get_task(self):
        self.ensure_one()
        tree_view_id = self.env.ref('grnlnd_task.view_task_tree3').id
        form_view_id = self.env.ref('project.view_task_form2').id
        self.ticket_task_count = self.env['project.task'].search_count([
            ('sale_contract_id', '=', self.id)])
        return {
            'type': 'ir.actions.act_window',
            'name': _('Service Tickets'),
            'view_mode': 'tree',
            'res_model': 'project.task',
            'views': [(tree_view_id, 'tree'), (form_view_id, 'form')],
            'domain': [('sale_contract_id', '=', self.id), ('contract_type', '=', self.contract_type)],
            "context": {'default_contract_type': self.contract_type},
            'target': 'current',
        }
    def action_create_task_ticket(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Service Tickets'),
            'view_mode': 'form',
            'res_model': 'project.task',
            'target': 'current',
            'context': {
                'default_sale_contract_id': self.id,
                'default_contract_customer_id': self.partner_id.id,
                'default_contract_type': self.contract_type,
            }
        }

    def prepare_invoice_line_items(self, task_for_contract, confirmed_invoice_ids=[]):
        result = []

        # Initialize a mapping of product_id to a list of service lines
        service_line_map = {}
        for records in task_for_contract:
            for line_item in records.contract_service_ids:
                if (line_item.name.id, line_item.location.id) not in service_line_map:
                    service_line_map[line_item.name.id, line_item.location.id] = []
                service_line_map[line_item.name.id, line_item.location.id].append(line_item)

        # Fetch all invoice lines related to these invoices
        invoice_lines = self.env['account.move.line'].search([
            ('move_id', 'in', confirmed_invoice_ids)
        ])

        invoiced_quantities = {
            line.product_id.id: line.quantity for line in invoice_lines
        }

        for contract_line in self.contract_line_ids:
            service_lines = service_line_map.get((contract_line.product_id.id, contract_line.location.id), [])
            service_quantity = sum(line.quantity for line in service_lines)

            # Get the invoiced quantity for this product
            invoiced_quantity = invoiced_quantities.get(contract_line.product_id.id, 0.0)
            # Check if the product has any posted invoice
            if invoiced_quantity > 0:
                # Skip product_uom_qty logic if posted invoice exists
                final_quantity = service_quantity
            else:
                # Calculate total quantity (service + invoice quantities)
                total_quantity = service_quantity + invoiced_quantity

                # Determine the final quantity using product_uom_qty logic
                if total_quantity < contract_line.product_uom_qty:
                    if contract_line.service_type == 'Optional':
                        final_quantity = total_quantity
                    else:
                        final_quantity = contract_line.product_uom_qty
                else:
                    final_quantity = total_quantity

            # Check service_type condition
            if not service_lines and contract_line.service_type == 'Optional':
                continue  # Skip optional products not in service lines

            # Append the result dictionary
            if final_quantity > 0:
                result.append((0, 0, {
                    'product_id': contract_line.product_id.id,
                    'name': contract_line.description,
                    'quantity': final_quantity,
                    'price_unit': contract_line.price_unit,
                    'tax_ids': contract_line.tax_ids,
                    'discount': contract_line.discount,
                    'location': contract_line.location.id
                }))

        return result

    def action_generate_invoice(self, start_date=None, end_date=None):
        """Generate a combined invoice for contract services with duplicate invoice prevention."""
        if not start_date or not end_date:
            raise ValueError("Start date and End date are required.")

        # Retrieve contract line items for required services
        contract_line_items = self.get_contract_line_items()

        # Get current billing period
        start_datetime = fields.Datetime.to_string(start_date)
        end_datetime = fields.Datetime.to_string(end_date)

        task_for_contract = self.get_contract_service_tickets(end_date=end_datetime, start_date=start_datetime)

        invoice_line_ids = []
        confirmed_invoice_ids = []
        uninvoiced_tasks = []

        # # Search for existing invoices linked to this contract within the billing period
        existing_invoices = self.env['account.move'].search([
            ('contract_origin', '=', self.id),
            ('move_type', '=', 'out_invoice'),
            ('start_date', '>=', start_datetime),
            ('end_date', '<=', end_datetime),
            ('state', '=', 'posted'),
        ])
        existing_invoices_draft = self.env['account.move'].search([
            ('contract_origin', '=', self.id),
            ('move_type', '=', 'out_invoice'),
            '|', ('invoice_date', '>=', start_datetime), ('invoice_date', '<=', end_datetime),
            '|', ('start_date', '=', start_datetime), ('end_date', '=', end_datetime),
        ])
        # # Handle Confirmed Invoices
        last_confirmed_invoice_date = None
        for invoice in existing_invoices:
            if invoice.state == 'posted':
                if not last_confirmed_invoice_date or invoice.invoice_date > last_confirmed_invoice_date:
                    last_confirmed_invoice_date = invoice.invoice_date
                confirmed_invoice_ids.append(invoice.id)
        #
        # Handle Draft Invoices: Delete existing drafts to prevent duplicates
        draft_invoices = existing_invoices_draft.filtered(lambda inv: inv.state == 'draft')
        if draft_invoices:
            for invoice in draft_invoices:
                self.env["account.move"].sudo().browse(invoice.id).unlink()
            self.invoice_count = self.env['account.move'].search_count([('contract_origin', '=', self.id)])

        if task_for_contract:
            # # Adjust start date for new invoices to avoid overlapping with confirmed invoices
            # if last_confirmed_invoice_date:
            # start_datetime = fields.Date.from_string(last_confirmed_invoice_date) + timedelta(days=1)
            uninvoiced_tasks = self.get_contract_service_tickets_without_invloce(end_date=end_datetime,
                                                                                 start_date=start_datetime)
            invoice_line_ids = self.prepare_invoice_line_items(uninvoiced_tasks, confirmed_invoice_ids)
        elif not task_for_contract and not confirmed_invoice_ids:
            for contract_line in self.contract_line_ids:
                if contract_line.service_type == "Required":
                    invoice_line_ids.append((0, 0, {
                        'product_id': contract_line.product_id.id,
                        'name': contract_line.description,
                        'quantity': contract_line.product_uom_qty,
                        'price_unit': contract_line.price_unit,
                        'tax_ids': contract_line.tax_ids,
                        'discount': contract_line.discount,
                        'location': contract_line.location.id
                    }))

        if not invoice_line_ids:
            raise UserError(_('No service tickets available to be invoiced.'))
        if invoice_line_ids:
            invoice = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': self.partner_id.id,
                'invoice_date': fields.Date.today(),
                'contract_origin': self.id,
                'invoice_payment_term_id': self.payment_terms_id.id if self.payment_terms_id else None,
                'currency_id': self.currency_id.id,
                'invoice_line_ids': invoice_line_ids,
                'customer_po': self.customer_po,
                'start_date': start_date,
                'end_date': end_date,
            })

            # Link service tickets to the invoice and update their state
            # for ticket in task_for_contract:
            #     ticket.write({'invoice_id': invoice.id, 'state': '05_invoiced'})
            if uninvoiced_tasks:
                for ticket in uninvoiced_tasks:
                    ticket.write({'invoice_id': invoice.id, 'state': '07_before_invoiced'})

            # Update invoice count
            self.invoice_count = self.env['account.move'].search_count([('contract_origin', '=', self.id)])

            # Return action to display the generated invoice
            return {
                'type': 'ir.actions.act_window',
                'name': _('Generated Invoice'),
                'view_mode': 'form',
                'res_model': 'account.move',
                'res_id': invoice.id,
                'target': 'current'
            }

    def calculate_product_quantities_and_check(self):
        # Initialize dictionaries to hold the quantities by product ID
        contract_quantities = defaultdict(float)
        task_quantities = defaultdict(float)
        invoiced_quantities = defaultdict(float)

        # Sum quantities from contract_line_ids
        for line in self.contract_line_ids:
            contract_quantities[line.product_id.id] += line.qty_ordered

        service_tickets = self.env['project.task'].search([
            ('sale_contract_id', '=', self.id)])
        for records in service_tickets:
            for line_items in records.contract_service_ids:
                task_quantities[line_items.name.id] += line_items.quantity

        confirmed_invoices = self.env['account.move'].search([
            ('contract_origin', '=', self.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
        ])

        for invoice in confirmed_invoices:
            for line in invoice.invoice_line_ids:
                invoiced_quantities[line.product_id.id] += line.quantity

        # Calculate missing quantities
        item_qty_count_dict = {}
        for product_id, contract_qty in contract_quantities.items():
            delivered_qty = task_quantities.get(product_id, 0.0)
            already_invoiced_qty = invoiced_quantities.get(product_id, 0.0)
            total_invoiced_or_delivered = delivered_qty + already_invoiced_qty

            # If total delivered and invoiced is less than the minimum contract quantity, calculate missing quantity
            if total_invoiced_or_delivered < contract_qty:
                missing_qty = contract_qty - total_invoiced_or_delivered
                item_qty_count_dict[product_id] = {
                    'contract_quantity': contract_qty,
                    'task_quantity': delivered_qty,
                    'already_invoiced_quantity': already_invoiced_qty,
                    'missing_quantity': missing_qty,
                }

        # Prepare invoice line values for missing quantities
        invoice_line_vals = []
        for product_id, discrepancy in item_qty_count_dict.items():
            contract_line = self.contract_line_ids.filtered(lambda l: l.product_id.id == product_id)
            if not contract_line:
                continue  # Skip if no matching contract line found

            missing_qty = discrepancy['missing_quantity']
            unit_price = contract_line.price_unit  # Assuming this field contains the unit price
            subtotal = missing_qty * unit_price
            invoice_line_vals.append((0, 0, {
                'product_id': product_id,
                'quantity': missing_qty,
                'price_unit': unit_price,
                'name': contract_line.description,
                'tax_ids': contract_line.tax_ids,
                'discount': contract_line.discount,
            }))

        # Create invoice for missing quantities
        if invoice_line_vals:
            self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': self.partner_id.id,
                'invoice_date': fields.Date.today(),
                'contract_origin': self.id,
                'invoice_payment_term_id': self.payment_terms_id.id if self.payment_terms_id else None,
                'currency_id': self.currency_id.id,
                'invoice_line_ids': invoice_line_vals,
            })
            self.invoice_count = self.env['account.move'].search_count([('contract_origin', '=', self.id)])

        return item_qty_count_dict


    def create_invoice_for_service_ticket_items(self, aggregated_quantities, contract_line_items, task_for_contract):
        invoice_line_ids = []
        for item in contract_line_items:
            product_id = item['product_id']
            if product_id in aggregated_quantities:
                item['quantity'] = aggregated_quantities[product_id]
                invoice_line_ids.extend([(0, 0, item)])
        if invoice_line_ids:
            invoice_obj = self.env['account.move'].create(
                {
                    'move_type': 'out_invoice',
                    'partner_id': self.partner_id.id,
                    'invoice_date': fields.date.today(),
                    'contract_origin': self.id,
                    'invoice_payment_term_id': self.payment_terms_id.id if self.payment_terms_id else None,
                    'currency_id': self.currency_id.id,
                    'invoice_line_ids': invoice_line_ids
                })
            for service in task_for_contract:
                service.write({"invoice_id": invoice_obj.id, "state": "05_invoiced"})
            self.invoice_count = self.env['account.move'].search_count([
                ('contract_origin', '=', self.id)])

    def get_contract_line_items(self):
        """Retrieve contract line items including service type."""
        contract_line_items = []
        for contract_line in self.contract_line_ids:
            contract_line_items.append({
                'product_id': contract_line.product_id.id,
                'name': contract_line.description,
                'quantity': contract_line.qty_ordered,
                'price_unit': contract_line.price_unit,
                'tax_ids': contract_line.tax_ids,
                'discount': contract_line.discount,
                'service_type': contract_line.service_type,
                'product_uom_qty': contract_line.product_uom_qty,
                'location': contract_line.location
            })
        return contract_line_items

    def get_service_ticket_line_items(self, task_for_contract, extra_qty_item_count_dict):
        """Aggregate quantities from service tickets."""
        aggregated_quantities = defaultdict(float)

        for task in task_for_contract:
            for service_item in task.contract_service_ids:
                product_id = service_item.name.id
                quantity = service_item.quantity
                if product_id:  # Ignore entries with product_id as False
                    aggregated_quantities[product_id] += quantity

        for key, values in extra_qty_item_count_dict.items():
            if key in aggregated_quantities:
                aggregated_quantities[key] -= values.get('extra_qty', 0)
        return aggregated_quantities

    def get_contract_service_tickets(self, end_date, start_date):
        task_for_contract = self.env["project.task"].search([
            ('sale_contract_id', '=', self.id),
            ('date_deadline', '>=', start_date),
            ('date_deadline', '<=', end_date),
            # ('invoice_id', '=', False)
        ])
        return task_for_contract

    def get_contract_service_tickets_without_invloce(self, end_date, start_date):
        task_for_contract = self.env["project.task"].search([
            ('sale_contract_id', '=', self.id),
            ('date_deadline', '>=', start_date),
            ('date_deadline', '<=', end_date),
            ('state', '!=', '05_invoiced'),
        ])
        return task_for_contract

    @api.model
    def subscription_contract_state_change(self):
        """ Automatic state change and create invoice """
        records = self.env['subscription.contracts'].search([])
        for rec in records:
            end_date = rec.date_end
            expiry_reminder = rec.contract_reminder
            expiry_warning_date = date_utils.subtract(end_date,
                                                      days=int(
                                                          expiry_reminder))
            current_date = fields.Date.today()
            next_invoice_date = rec.next_invoice_date
            if expiry_warning_date <= current_date <= end_date:
                rec.write({'state': 'Expire Soon'})
            if end_date < current_date:
                rec.write({'state': 'Expired'})
            if next_invoice_date == current_date and rec.state != 'Cancelled':
                contract_line_items = rec.get_contract_line_items()

                today_date = fields.Datetime.now()
                first_day_of_current_month = today_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                last_day_previous_month = first_day_of_current_month - timedelta(days=1)

                # Start date: first day of the previous month at midnight
                start_date = last_day_previous_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

                # End date: last day of the previous month at the last moment
                end_date = last_day_previous_month.replace(hour=23, minute=59, second=59, microsecond=999999)

                # Convert to Odoo datetime string format if needed
                start_datetime = fields.Datetime.to_string(start_date)
                end_datetime = fields.Datetime.to_string(end_date)
                task_for_contract = rec.get_contract_service_tickets(end_date=end_datetime, start_date=start_datetime)
                # if task_for_contract:
                #     extra_qty_item_count_dict = rec.calculate_product_quantities_and_check()  # method to calculate extra quantity of service tickets and create invoice
                #     aggregated_quantities = rec.get_service_ticket_line_items(task_for_contract, extra_qty_item_count_dict)
                #     rec.create_invoice_for_service_ticket_items(aggregated_quantities, contract_line_items, task_for_contract)

    @api.model_create_multi
    def create(self, vals_list):
        # orders = self.browse()
        for vals in vals_list:
            if 'company_id' in vals:
                self = self.with_company(vals['company_id'])
            if vals.get('name', 'New') == 'New':
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['date_start'])
                ) if 'date_start' in vals else None
                if vals['contract_type'] == 'Non Hazardous':
                    vals['name'] = self.env['ir.sequence'].next_by_code('non.hazardous.contract',
                                                                        sequence_date=seq_date) or '/'
                else:
                    vals['name'] = self.env['ir.sequence'].next_by_code('hazardous.contract',
                                                                        sequence_date=seq_date) or '/'
        return super().create(vals_list)

    def action_to_confirm(self):
        """ Confirm the Contract """
        super().action_to_confirm()
        self.action_lock()

    def action_send_contract_email(self):
        self.ensure_one()

        # Open the wizard for sending the email with the template
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send Contract for Signature'),
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_model': 'subscription.contracts',
                'default_res_ids': [self.id],  # Updated to use a list
                'default_use_template': True,
                'default_template_id': self.env.ref('grnlnd_task.email_template_contract_signature').id,
                'default_composition_mode': 'comment',
            },
        }

    def open_generate_invoice_wizard(self):
        """Open the wizard for generating invoice with date inputs"""
        # Calculate the first day of the current month
        first_day_of_month = date.today().replace(day=1)

        return {
            'name': 'Generate Invoice',
            'type': 'ir.actions.act_window',
            'res_model': 'contract.invoice.wizard',
            'view_mode': 'form',
            'target': 'new',  # Opens the form in a modal
            'context': {
                'default_start_date': first_day_of_month,
                'default_end_date': fields.Date.context_today(self),
                'active_ids': self.ids,
            }
        }

    def action_generate_service_summary(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Generate Service Summary Report',
            'res_model': 'subscription.contracts.summary.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_contract_id': self.id,
                'default_company_id': self.company_id.id or False,
            },
    }

    def generate_service_summary_report(self, start_date, end_date):
        """Generate the service ticket summary report based on the specified date range."""
        self.ensure_one()
        if not start_date or not end_date:
            raise UserError("Start date and End date are required.")

        # Prepare report data using a custom report class
        report_data = {
            'doc_ids': self.ids,
            'doc_model': 'subscription.contracts',
            'docs': self,
            'start_date': start_date.strftime('%d/%b/%Y') if start_date else 'N/A',
            'end_date': end_date.strftime('%d/%b/%Y') if end_date else 'N/A',
        }
        return self.env.ref('grnlnd_task.action_service_summary_report_contract').report_action(self, data=report_data)

class SubscriptionContractLines(models.Model):
    """ Add subscription contract line """
    _inherit = 'subscription.contracts.line'

    location = fields.Many2one('sale.order.location', 'Location')
    # name_ar = fields.Char(string="Description(Arabic)",
    #                       related="product_id.name_ar", store=True,
    #                       readonly=False)
    product_domain = fields.Binary(compute="_compute_product_domain")
    service_type = fields.Selection([
        ('Required', 'Required'),
        ('Optional', 'Optional'),
    ], string='Service Type', default='Required', copy=False, tracking=True,
        help='Type of service')

    name_ar = fields.Char(
        string="Description (Arabic)",
        compute='_compute_name_ar',
        store=True, readonly=False
    )

    product_id = fields.Many2one('product.product', string="Product")

    @api.depends('product_id')
    def _compute_name_ar(self):
        for line in self:
            line.name_ar = line.product_id.product_tmpl_id.name_ar if line.product_id else False

    @api.depends('subscription_contract_id')
    def _compute_product_domain(self):
        ids_list = []
        for rec in self:
            if rec.subscription_contract_id:
                if rec.subscription_contract_id.contract_type == "Non Hazardous":
                    ids_list = [product.id for product in self.env['product.product'].search(
                        [('non_hazardous', '=', True)])]
                else:
                    ids_list = [product.id for product in self.env['product.product'].search(
                        [('hazardous', '=', True)])]
                rec.product_domain = [('id', 'in', ids_list)]
            else:
                rec.product_domain = []



class ContractInvoiceWizard(models.TransientModel):
    _name = 'contract.invoice.wizard'
    _description = 'Contract Invoice Wizard'

    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)

    def action_generate_invoice(self):
        """Call the generate invoice method from the contract with the provided dates"""
        active_ids = self.env.context.get('active_ids', [])
        contracts = self.env['subscription.contracts'].browse(active_ids)
        for contract in contracts:
           return contract.action_generate_invoice(self.start_date, self.end_date)


class SubscriptionContractsSummaryWizard(models.TransientModel):
    _name = 'subscription.contracts.summary.wizard'
    _description = 'Service Summary Report Wizard'

    contract_id = fields.Many2one('subscription.contracts', string="Contract", readonly=True)
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)

    def action_generate_report(self):
        """Generate and download the service summary report as a PDF."""
        self.ensure_one()
        report_action = self.contract_id.generate_service_summary_report(self.start_date, self.end_date)
        # Ensure the report action triggers a download
        report_action['type'] = 'ir.actions.report'
        return report_action


class ReportServiceSummary(models.AbstractModel):
    _name = 'report.grnlnd_task.report_service_summary_contract'

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data and not docids:
            raise UserError("No report data or document IDs provided.")

        # Use docids if data['doc_ids'] is not available (gear icon case)
        contract_id = data.get('doc_ids', docids[0] if docids else None)
        if not contract_id:
            raise UserError("No contract specified for report generation.")

        contract = self.env['subscription.contracts'].browse(contract_id)
        if not contract:
            raise UserError("No contract found for report generation.")

        # Handle dates from wizard
        if not data or 'start_date' not in data or 'end_date' not in data:
            raise UserError("Please specify start and end dates via the wizard.")

        start_date = data['start_date']  # Already in %d/%b/%Y format
        end_date = data['end_date']      # Already in %d/%b/%Y format

        service_tasks = self.env['project.task'].search([
            ('sale_contract_id', '=', contract.id),
            ('date_deadline', '>=', datetime.strptime(start_date, '%d/%b/%Y').date()),
            ('date_deadline', '<=', datetime.strptime(end_date, '%d/%b/%Y').date()),
            ('date_deadline', '!=', False),
        ])

        if not service_tasks:
            raise UserError("No service tickets found for the specified date range for contract %s." % contract.name)

        service_dict = {}
        for task in service_tasks:
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
                    'service_ticket_date': task.date_deadline.strftime('%d/%b/%Y') if task.date_deadline else 'N/A',
                    'service_ticket_number': task.service_ticket_number or 'N/A',
                    'location': service_line.location.name if service_line.location else '-',
                    'driver_name': task.driver_id.name if task.driver_id else 'N/A',
                    'vehicle_number': task.vehicle_number.name if task.vehicle_number else 'N/A',
                    'service_qty': service_line.quantity or 0.0,
                })
                service_dict[product_id]['total_qty'] += service_line.quantity or 0.0

        service_data = []
        for product_id, product_info in service_dict.items():
            product_info['entries'].sort(key=itemgetter('location'))
            service_data.append({
                'service_name': product_info['service_name'],
                'entries': product_info['entries'],
                'total_qty': product_info['total_qty'],
            })

        return {
            'doc_model': 'subscription.contracts',
            'doc_ids': [contract.id],
            'doc': contract,
            'start_date': start_date,
            'end_date': end_date,
            'services': service_data,
        }

class ReportServiceTicketTemplate(models.AbstractModel):
    _name = 'report.grnlnd_task.report_service_ticket_template'
    _description = 'Service Ticket Report Template'

    @api.model
    def _get_report_values(self, docids, data=None):
        tasks = self.env['project.task'].browse(docids).sorted(key=lambda t: t.date_deadline or fields.Date.today())
        manual_tickets = tasks.filtered(lambda t: t.ticket_type == 'manual')
        if manual_tickets:
            raise UserError(_('Please deselect manual tickets. Only digital tickets can be printed.'))
        return {
            'doc_ids': docids,
            'doc_model': 'project.task',
            'docs': tasks,
        }