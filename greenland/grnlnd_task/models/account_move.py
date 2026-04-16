# -*- coding: utf-8 -*-

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError
import num2words
import re
from operator import itemgetter
import base64
import qrcode
from io import BytesIO
from datetime import datetime
import hashlib
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    location = fields.Many2one('sale.order.location', 'Location')
    line_description = fields.Char(
        string="Line Description",
    )
    name_ar = fields.Char(string="Product Name (Arabic)", related="product_id.name_ar", store=True,
                          readonly=True)
    
    @api.constrains('product_uom_id')
    def _check_product_uom_category_id(self):
        pass
        
    def unlink(self):
        if self.env.context.get('skip_service_ticket_reversion'):
            return super(AccountMoveLine, self).unlink()
            
        lines_info = []
        for line in self:
            if line.move_id.is_service_ticket_invoice and line.move_id.state == 'draft':
                lines_info.append({
                    'product_id': line.product_id.id,
                    'location_id': line.location.id if line.location else False,
                    'move_id': line.move_id.id,
                    'quantity': line.quantity,
                    'line_id': line.id,
                })
                
        result = super(AccountMoveLine, self).unlink()
        
        if lines_info:
            self._revert_service_ticket_status(lines_info)
            
        return result
    
    def _revert_service_ticket_status(self, lines_info):
        ProjectTask = self.env['project.task']
        
        for line_info in lines_info:
            invoice = self.env['account.move'].browse(line_info['move_id'])
            
            tickets = ProjectTask.search([
                ('invoice_id', '=', invoice.id),
                ('invoice_state', '=', 'draft')
            ])
            
            if not tickets:
                continue
            
            tickets_to_revert = self.env['project.task']
            
            nhz_tickets = tickets.filtered(lambda t: t.contract_type == 'Non Hazardous')
            
            for ticket in nhz_tickets:
                for service in ticket.contract_service_ids:
                    if (service.name.id == line_info['product_id'] and 
                        (service.location.id if service.location else False) == line_info['location_id']):
                        tickets_to_revert |= ticket
                        break
            
            hzd_tickets = tickets - nhz_tickets
            
            for ticket in hzd_tickets:
                for service in ticket.contract_service_ids:
                    if (service.name.id == line_info['product_id'] and 
                        (service.location.id if service.location else False) == line_info['location_id']):
                        tickets_to_revert |= ticket
                        break
            
            if tickets_to_revert:
                services_to_remove = []
                for ticket in tickets_to_revert:
                    for service in ticket.contract_service_ids:
                        services_to_remove.append({
                            'product_id': service.name.id,
                            'location_id': service.location.id if service.location else False
                        })
                
                lines_to_delete = self.env['account.move.line']
                for invoice_line in invoice.invoice_line_ids:
                    for service in services_to_remove:
                        if (invoice_line.product_id.id == service['product_id'] and
                            (invoice_line.location.id if invoice_line.location else False) == service['location_id'] and
                            invoice_line.id != line_info.get('line_id')):
                            lines_to_delete |= invoice_line
                            break
                
                if lines_to_delete:
                    lines_to_delete.with_context(skip_service_ticket_reversion=True).unlink()
                
                for ticket in tickets_to_revert:
                    ticket.write({
                        'invoice_id': False,
                        'state': '03_approved'
                    })

    @api.depends('product_id')
    def _compute_name(self):
        for line in self:
            if not line.product_id:
                line.name = line.line_description or ''
                continue

            partner_lang = line.move_id.partner_id.lang if line.move_id.partner_id else 'en_US'
            product_lang = line.product_id.with_context(lang=partner_lang)
            name = product_lang.name or ""
            name_lines = name.splitlines()
            name = name_lines[0] if name_lines else ''

            bracket_index = name.find(']')
            if bracket_index != -1:
                name = name[bracket_index + 1:].strip()
            line.name = name or line.line_description or ''

class AccountMove(models.Model):
    _inherit = "account.move"
    
    is_service_ticket_invoice = fields.Boolean(
        string="Service Ticket Invoice",
        default=False,
        help="Indicates if this invoice was created from service tickets"
    )

    customer_po = fields.Char("Customer PO")
    start_date = fields.Date(string="Start Date")
    end_date = fields.Date(string="End Date")
    invoice_number_arabic = fields.Char(string="Arabic Invoice Number", compute="_compute_invoice_number_arabic")

    description_all = fields.Char(
        string="Line Description",
        compute="_compute_line_description",
        store=True
    )
    show_product_name_ar = fields.Boolean(
        string="Show Product Arabic Name",
        default=False,
        help="Enable this to display product Arabic name on the invoice report."
    )
    
    is_error_invoice = fields.Boolean(
        string="Error Invoice",
        default=False,
        help="Mark this credit note as an error reversal. The original reversed invoice will be hidden from customer statements.",
        tracking=True
    )
    
    # Search fields for service-based invoice search
    service_names = fields.Char(
        string="Service Names",
        compute='_compute_service_names',
        store=True,
        search='_search_service_names'
    )
    
    # Employee-wise grouped journal entry fields
    group_id = fields.Many2one(
        'account.move.group',
        string='Entry Group',
        help='Group for employee-wise journal entries',
        ondelete='set null',
        copy=False
    )
    sequence_in_group = fields.Integer(
        string='Sequence in Group',
        default=1,
        help='Order of this entry within its group'
    )
    
    _sql_constraints = [
        ('unique_ref', 'unique(ref)', 
         'Reference must be unique. A Journal Entry with this reference already exists.')
    ]
    
    def unlink(self):
        """Override unlink to clear invoice_id from linked service tickets before deletion."""
        # Find all service tickets linked to these invoices
        linked_tasks = self.env['project.task'].search([
            ('invoice_id', 'in', self.ids)
        ])
        
        if linked_tasks:
            # Clear the invoice_id and reset state for re-linking
            linked_tasks.with_context(bypass_service_validation=True).write({
                'invoice_id': False,
                'state': '03_approved'
            })
        
        return super(AccountMove, self).unlink()
    

    @api.depends('invoice_line_ids.product_id.name', 'invoice_line_ids.product_id.default_code', 'invoice_line_ids.product_id.name_ar', 'invoice_line_ids.name', 'invoice_line_ids.line_description')
    def _compute_service_names(self):
        for move in self:
            service_names = []
            for line in move.invoice_line_ids:
                if line.product_id:
                    if line.product_id.name:
                        service_names.append(line.product_id.name)
                    if line.product_id.default_code:
                        service_names.append(line.product_id.default_code)
                    if line.product_id.name_ar:
                        service_names.append(line.product_id.name_ar)
                if line.name:
                    service_names.append(line.name)
                if line.line_description:
                    service_names.append(line.line_description)
            move.service_names = ' '.join(set(service_names))
    
    def _search_service_names(self, operator, value):
        if operator == 'ilike' and value:
            search_terms = value.strip()
            if not search_terms:
                return []
            
            # Primary search - exact match like SQL ILIKE
            domain = [
                '|', '|', '|', '|', '|',
                ('invoice_line_ids.product_id.name', 'ilike', search_terms),
                ('invoice_line_ids.product_id.default_code', 'ilike', search_terms),
                ('invoice_line_ids.product_id.name_ar', 'ilike', search_terms),
                ('invoice_line_ids.name', 'ilike', search_terms),
                ('invoice_line_ids.line_description', 'ilike', search_terms)
            ]
            
            # Additional search for partial matches to catch more results
            domain.extend([
                '|', '|', '|', '|', '|',
                ('invoice_line_ids.product_id.name', 'ilike', f'%{search_terms}%'),
                ('invoice_line_ids.product_id.default_code', 'ilike', f'%{search_terms}%'),
                ('invoice_line_ids.product_id.name_ar', 'ilike', f'%{search_terms}%'),
                ('invoice_line_ids.name', 'ilike', f'%{search_terms}%'),
                ('invoice_line_ids.line_description', 'ilike', f'%{search_terms}%')
            ])
            
            return domain
        return []
    
    def debug_service_search(self, service_name):
        """Debug method to compare search results with SQL query"""
        domain = self._search_service_names('ilike', service_name)
        if domain:
            invoices = self.search(domain)
            return {
                'domain': domain,
                'count': len(invoices),
                'invoice_ids': invoices.ids,
                'invoice_numbers': invoices.mapped('name')
            }
        return {'error': 'No domain generated'}

    def _generate_zatca_qr_code(self):
        """
        Generate ZATCA Phase 2 compliant QR code with cryptographic stamp
        """
        if not self:
            return False

        def tlv_encode(tag, value):
            value_bytes = value.encode('utf-8')
            length = len(value_bytes)
            if length > 255:
                length_bytes = length.to_bytes(2, 'big')  # Convert to 2 bytes
                return bytes([tag]) + length_bytes + value_bytes
            else:
                return bytes([tag, length]) + value_bytes


        seller_name = self.company_id.name or ''
        vat_number = self.company_id.vat or ''
        invoice_timestamp = self.invoice_date.strftime('%Y-%m-%dT%H:%M:%SZ') if self.invoice_date else ''
        total_amount = f"{self.amount_total:.2f}"
        tax_amount = f"{self.amount_tax:.2f}"
        invoice_uuid = self.name

        invoice_data_string = f"{seller_name}{vat_number}{invoice_timestamp}{total_amount}{tax_amount}{invoice_uuid}"
        invoice_hash = hashlib.sha256(invoice_data_string.encode()).hexdigest()

        previous_invoice_hash = hashlib.sha256("previous_invoice_data".encode()).hexdigest()

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )

        signature = private_key.sign(
            invoice_hash.encode(),
            padding.PKCS1v15(),
            hashes.SHA256()
        )

        signature_b64 = base64.b64encode(signature).decode()

        tlv_data = b''.join([
            tlv_encode(1, seller_name),
            tlv_encode(2, vat_number),
            tlv_encode(3, invoice_timestamp),
            tlv_encode(4, total_amount),
            tlv_encode(5, tax_amount),
            tlv_encode(6, invoice_uuid),
            tlv_encode(7, invoice_hash),
            tlv_encode(8, previous_invoice_hash),
            tlv_encode(9, signature_b64)
        ])

        qr_content = base64.b64encode(tlv_data).decode('utf-8')

        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_content)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buffered = BytesIO()
        img.save(buffered, format="PNG")

        img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        zatca_qr_code = f'data:image/png;base64,{img_str}'
        return zatca_qr_code

    def button_cancel(self):
        for move in self:
            if move.state == 'draft' and move.start_date and move.end_date:
                task_line_cancel = self.env["project.task"].search([
                    ('date_deadline', '>=', move.start_date),
                    ('date_deadline', '<=', move.end_date),
                    ('invoice_id', '=', move.id),
                    ('state', '!=', '05_invoiced')
                ])
                if task_line_cancel:
                    task_line_cancel.write({
                        'invoice_id': None,
                        'state': '06_cancelled',
                    })
        
        moves_to_reset_draft = self.filtered(lambda x: x.state == 'posted')
        if moves_to_reset_draft:
            moves_to_reset_draft.button_draft()

        if any(move.state != 'draft' for move in self):
            raise UserError(_("Only draft journal entries can be cancelled."))

        self.write({'auto_post': 'no', 'state': 'cancel'})

    def action_post(self):
        # Handle invoice reversals - when a reversal is posted, unlink service tickets from the original invoice
        # Batch process for better performance
        refunds = self.filtered(
            lambda m: m.move_type in ('out_refund', 'in_refund') and m.reversed_entry_id
        )
        if refunds:
            original_invoices = refunds.mapped('reversed_entry_id')
            linked_tasks = self.env['project.task'].search([
                ('invoice_id', 'in', original_invoices.ids)
            ])
            if linked_tasks:
                linked_tasks._handle_invoice_reversal()

        for move in self:
            if move.start_date and move.end_date:
                task_line_confirm = self.env["project.task"].search([
                    ('date_deadline', '>=', move.start_date),
                    ('date_deadline', '<=', move.end_date),
                    ('invoice_id', '=', move.id),
                    ('state', '=', '07_before_invoiced')
                ])
                if task_line_confirm:
                    task_line_confirm.write({
                        'state': '05_invoiced',
                    })

        moves_with_payments = self.filtered('payment_id')
        other_moves = self - moves_with_payments
        if moves_with_payments:
            moves_with_payments.payment_id.action_post()
        if other_moves:
            other_moves._post(soft=False)
        return False

    def preview_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': self.get_portal_url(report_type='pdf'),
        }

    @api.depends('invoice_line_ids.name')
    def _compute_line_description(self):
        for move in self:
            for line in move.invoice_line_ids:
                if line.name:
                    # Remove content within square brackets and any extra spaces
                    line.line_description = re.sub(r'\[.*?\]\s*', '', line.name)
                else:
                    line.line_description = ""

    @api.depends('name')
    def _compute_invoice_number_arabic(self):
        for record in self:
            if record.name:
                numeric_part = record.name.split('/', 1)[-1]
                record.invoice_number_arabic = record._translate_to_arabic(numeric_part)

    @staticmethod
    def _translate_to_arabic(text):
        arabic_numbers = {'0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤', '5': '٥', '6': '٦', '7': '٧', '8': '٨',
                          '9': '٩'}
        return ''.join(arabic_numbers.get(char, char) for char in text)

    def amount_in_words(self):

        whole_number = int(self.amount_total)
        fractional_number = round((self.amount_total - whole_number) * 100)

        # Convert whole number to words
        whole_in_words = num2words.num2words(whole_number, lang='en')
        # Convert fractional part to words
        fractional_in_words = num2words.num2words(fractional_number, lang='en')

        # Combine both parts and append "Riyals" and "Halalas"
        return f"{whole_in_words.title()} Riyals and {fractional_in_words.title()} Halalas"

    def amount_in_words_ar(self):
        """Convert amount to Arabic words with Riyals and Halalas."""
        whole_number = int(self.amount_total)
        fractional_number = round((self.amount_total - whole_number) * 100)

        # Convert whole number and fractional part to Arabic words
        whole_in_words = num2words.num2words(whole_number, lang='ar')
        fractional_in_words = num2words.num2words(fractional_number, lang='ar')

        # Append currency units
        return f"{whole_in_words} ريال و {fractional_in_words} هللة"

    def action_create_entry_below(self):
        """Create a new journal entry below the current one in the same group"""
        self.ensure_one()
        
        # Ensure this is a journal entry (not invoice)
        if self.move_type != 'entry':
            raise UserError(_("This action is only available for Journal Entries."))
        
        # Validate partner is set
        if not self.partner_id:
            raise UserError(_("Please select a Partner/Employee before creating a grouped entry."))
        
        # Get or create group
        if not self.group_id:
            # Create a new group for this entry
            group = self.env['account.move.group'].find_or_create_group(
                self.partner_id.id,
                self.journal_id.id
            )
            # Add current entry to the group
            self.write({
                'group_id': group.id,
                'sequence_in_group': 1
            })
        else:
            group = self.group_id
        
        # Get the next sequence in group
        max_sequence = max(group.move_ids.mapped('sequence_in_group') or [0])
        
        # Return action to create new entry
        return {
            'name': _('New Journal Entry'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_move_type': 'entry',
                'default_group_id': group.id,
                'default_partner_id': self.partner_id.id,
                'default_journal_id': self.journal_id.id,
                'default_sequence_in_group': max_sequence + 1,
            }
        }
    
    def action_view_group(self):
        """Open the group form view showing all entries"""
        self.ensure_one()
        if not self.group_id:
            raise UserError(_("This entry is not part of a group."))
        
        return {
            'name': _('Grouped Journal Entries'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.group',
            'res_id': self.group_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_create_group(self):
        """Create a group for ungrouped entries"""
        self.ensure_one()
        
        if self.group_id:
            raise UserError(_("This entry is already part of a group."))
        
        if self.move_type != 'entry':
            raise UserError(_("Only Journal Entries can be grouped."))
        
        if not self.partner_id:
            raise UserError(_("Please select a Partner/Employee before creating a group."))
        
        # Create group
        group = self.env['account.move.group'].find_or_create_group(
            self.partner_id.id,
            self.journal_id.id
        )
        
        # Add this entry to the group
        self.write({
            'group_id': group.id,
            'sequence_in_group': 1
        })
        
        return self.action_view_group()

    def action_reverse(self):
        """Override the standard reverse action to handle existing draft credit notes"""
        self.ensure_one()
        
        # Find any existing draft credit notes for this invoice
        existing_credit_notes = self.env['account.move'].search([
            ('reversed_entry_id', '=', self.id),
            ('state', '=', 'draft')
        ])
        
        # If there are existing draft credit notes, delete them
        if existing_credit_notes:
            existing_credit_notes.unlink()
        
        # Call the standard reverse action
        return  super().action_reverse()

    def get_service_ticket_summary_data(self):
        self.ensure_one()
        tasks = self.env['project.task'].search([('invoice_id', '=', self.id)])
        service_dict = {}
        
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


        service_data = []
        for product_id, product_info in service_dict.items():
            product_info['entries'].sort(key=itemgetter('location'))
            service_data.append({
                'service_name': product_info['service_name'],
                'entries': product_info['entries'],
                'total_qty': product_info['total_qty'],
            })
        return service_data

class ReportServiceTicketSummary(models.AbstractModel):
    _name = 'report.grnlnd_task.report_service_summary'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['account.move'].browse(docids)
        # This report was originally designed for a single doc (based on original code using docids for 'invoice' variable name and assuming singleton in search)
        # However, to support standard behavior, we should ideally handle docs iteration if we were rewriting fully.
        # But keeping consistent with original behavior:
        
        # Original code Analysis:
        # invoice = self.env['account.move'].browse(docids) --> implies docids could be multiple, but 'invoice.id' usage in search implies singleton or it fails.
        # So we treat it as singleton or use the first one if multiple (though browse(docids).id fails).
        
        # We will iterate and return data for the first one as per original implication, or better, we support the loop if the template supports it.
        # The template 'report_service_summary' uses 'doc' (singular). 
        # So we likely just process the first doc id.
        
        invoice = docs[0] if docs else self.env['account.move']
        service_data = invoice.get_service_ticket_summary_data() if invoice else []
        return {
            'doc_model': 'account.move',
            'doc_ids': docids,
            'doc': invoice,
            'services': service_data,
        }

class AccountMoveSend(models.TransientModel):
    _inherit = 'account.move.send'

    def default_get(self, fields_list):
        res = super(AccountMoveSend, self).default_get(fields_list)
        custom_template = self.env.ref('grnlnd_task.email_template_invoice_service_rendered')
        if custom_template:
            res['mail_template_id'] = custom_template.id
        return res
