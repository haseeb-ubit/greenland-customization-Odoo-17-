from odoo import models, fields, api, _
from odoo.exceptions import UserError

class LinkInvoiceWizard(models.TransientModel):
    _name = 'link.invoice.wizard'
    _description = 'Link Service Tickets to Invoice'

    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    invoice_id = fields.Many2one(
        'account.move',
        string='Invoice',
        required=True,
        domain="[('partner_id', '=', partner_id), ('state', '=', 'posted'), ('payment_state', '!=', 'reversed'), ('move_type', '=', 'out_invoice')]"
    )
    task_ids = fields.Many2many('project.task', string='Service Tickets')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self._context.get('active_ids')
        if not active_ids:
             return res
             
        tasks = self.env['project.task'].browse(active_ids)
        
        # 1. Validation: Single Customer
        customers = tasks.mapped('contract_customer_id')
        if len(customers) > 1:
            raise UserError(_("Select tickets from a single customer only."))
        if not customers:
                raise UserError(_("Selected tickets have no customer assigned."))

        # 2. Safety net in case JS fails: block only tickets linked to a confirmed invoice
        posted = tasks.filtered(lambda t: t.invoice_state == 'posted')
        if posted:
            raise UserError(_(
                "The following tickets are already linked to a confirmed invoice "
                "and cannot be re-linked:\n%s"
            ) % ', '.join(posted.mapped('service_ticket_number')))

        res.update({
            'task_ids': [(6, 0, active_ids)],
            'partner_id': customers[0].id
        })
        return res

    def action_link_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
             raise UserError(_("Please select an invoice."))
        
        aggregated_data = {}
        for task in self.task_ids:
            for service in task.contract_service_ids:
                key = (service.name.id, service.product_uom_id.id)
                if key not in aggregated_data:
                    aggregated_data[key] = {
                        'product_id': service.name.id,
                        'product_uom_id': service.product_uom_id.id,
                        'quantity': 0.0,
                        'ticket_refs': []
                    }
                aggregated_data[key]['quantity'] += service.quantity
                aggregated_data[key]['ticket_refs'].append(task.service_ticket_number or str(task.id))

        new_lines_vals = []
        for key, data in aggregated_data.items():
            product = self.env['product.product'].browse(data['product_id'])
            ticket_refs_str = ', '.join(data['ticket_refs'])
            # Limit description length if too many tickets
            if len(ticket_refs_str) > 50:
                 ticket_refs_str = f"{len(data['ticket_refs'])} Tickets"
            
            new_lines_vals.append({
                'move_id': self.invoice_id.id,
                'product_id': data['product_id'],
                'quantity': data['quantity'],
                'product_uom_id': data['product_uom_id'],
                'price_unit': 0.0,
                'name': f"{product.name} (Linked: {ticket_refs_str})",
            })

        for task in self.task_ids:
            task.write({
                'invoice_id': self.invoice_id.id,
                'state': '05_invoiced'
            })
        return {'type': 'ir.actions.act_window_close'}
