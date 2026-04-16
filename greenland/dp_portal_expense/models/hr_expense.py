from odoo import models, fields, api
from odoo.exceptions import ValidationError

class HrExpense(models.Model):
    _inherit = 'hr.expense'
    
    def get_printable_image(self):
        """
        Return a safe data URI for the main attachment image.
        Converts WebP/CMYK/etc to PNG using Pillow to ensure wkhtmltopdf compatibility.
        """
        self.ensure_one()
        attachment = self.message_main_attachment_id
        if not attachment or not attachment.datas or attachment.mimetype == 'application/pdf':
            return False

        try:
            # Check if it's already a safe format (e.g. PNG/JPEG RGB)
            # But since user reported JPEG fails (likely CMYK), we process all non-trivial images
            # or just process everything to be safe. WebP DEFINITELY needs conversion.
            
            import io
            import base64
            from PIL import Image
            # Explicitly import plugins to ensure registration
            from PIL import WebPImagePlugin, JpegImagePlugin, PngImagePlugin
            
            # Decode existing data
            image_data = base64.b64decode(attachment.datas)
            if not image_data:
                 return False
            
            image_stream = io.BytesIO(image_data)
            
            try:
                img = Image.open(image_stream)
                img.load() # Force load to check file integrity
            except Exception:
                return False

            # If it's WebP, or CMYK, or anything weird -> Convert to PNG (RGB)
            if img.format == 'WEBP' or img.mode == 'CMYK' or attachment.mimetype == 'image/webp':
                # Convert to RGB (standard PNG)
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGB')
                
                output_stream = io.BytesIO()
                img.save(output_stream, format='PNG')
                new_data = base64.b64encode(output_stream.getvalue()).decode('utf-8')
                return f"data:image/png;base64,{new_data}"
            
            # If original was fine (e.g. simple JPEG/PNG), return original to save processing
            return f"data:{attachment.mimetype};base64,{attachment.datas.decode('utf-8')}"
            
        except Exception:
            return False


    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        help="Select the vendor for this expense",  
        tracking=True,
        required=True,
        domain="[('x_studio_contact_type', '=', 'Vendor'), ('is_company', '=', True)]",
        copy=False,
    )
    vendor_vat = fields.Char(
        string='VAT Number',
        help="Vendor VAT number — auto-fetched from Vendor",
        store=True
    )
    reference = fields.Char(
        string='Invoice/Bill #',
        help="Invoice or bill reference number from vendor",
        tracking=True,
        required=False,
    )
    date = fields.Date(string="Expense Date", default=False)

    @api.constrains('vendor_id')
    def _check_vendor_is_vendor(self):
        """Ensure selected partner is a Vendor, not a Customer"""
        for expense in self:
            if expense.vendor_id:
                if expense.vendor_id.x_studio_contact_type != 'Vendor':
                    raise ValidationError(
                        f"'{expense.vendor_id.name}' is not a Vendor. "
                        "Please select a contact with Contact Type = 'Vendor'."
                    )

    @api.constrains('vendor_id', 'vendor_vat')
    def _check_vat_matches_vendor(self):
        """Ensure VAT number matches the selected vendor's VAT"""
        for expense in self:
            if expense.vendor_id and expense.vendor_vat:
                vendor_vat = (expense.vendor_id.vat or '').replace(' ', '').strip()
                entered_vat = expense.vendor_vat.replace(' ', '').strip()

                if vendor_vat and entered_vat != vendor_vat:
                    raise ValidationError(
                        f"VAT Number '{expense.vendor_vat}' does not match the selected vendor's VAT "
                        f"'{expense.vendor_id.vat}'. Please correct the VAT number or select a different vendor."
                    )
            elif expense.vendor_id and not expense.vendor_vat:
                # If vendor is selected but VAT is empty, auto-fill it
                # This is handled in onchange, but as a safety net:
                pass



    @api.onchange('vendor_id')
    def _onchange_vendor_id(self):
        """Update VAT when vendor is selected, validate it's a Vendor"""
        if self.vendor_id:
            # Check if selected partner is a Vendor
            if self.vendor_id.x_studio_contact_type != 'Vendor':
                # Clear the selection and show warning
                partner_name = self.vendor_id.name
                self.vendor_id = False
                self.vendor_vat = False
                return {
                    'warning': {
                        'title': 'Invalid Selection',
                        'message': f"'{partner_name}' is a Customer, not a Vendor. Please select a Vendor."
                    }
                }
            self.vendor_vat = self.vendor_id.vat
        else:
            self.vendor_vat = False

    @api.onchange('vendor_vat')
    def _onchange_vendor_vat(self):
        """Filter vendor dropdown and auto-select on exact match"""
        if not self.vendor_vat:
            self.vendor_id = False
            return {}

        clean_vat = self.vendor_vat.replace(' ', '').strip()

        # STRICT domain: Only Vendors (x_studio_contact_type='Vendor') and Companies
        base_domain = [
            ('x_studio_contact_type', '=', 'Vendor'),
            ('is_company', '=', True),
        ]

        # SEARCH 1: Exact match
        vendor = self.env['res.partner'].search(base_domain + [
            '|',
            ('vat', '=', self.vendor_vat),
            ('vat', '=', clean_vat)
        ], limit=1)

        if vendor:
            self.vendor_id = vendor
            return {}

        # SEARCH 2: Partial match
        partners = self.env['res.partner'].search(base_domain + [
            '|',
            ('vat', 'ilike', self.vendor_vat),
            ('vat', 'ilike', clean_vat)
        ], limit=20)

        # Update domain for user to select from partial matches
        return {
            'domain': {
                'vendor_id': [('id', 'in', partners.ids)] if partners else base_domain
            }
        }

    def _prepare_payments_vals(self):
        self.ensure_one()
        vals = dict(super()._prepare_payments_vals() or {})

        vendor = self.vendor_id
        vendor_vat = self.vendor_vat

        vals.update({
            'partner_id': vendor.id if vendor else False,
            'partner_vat': vendor_vat or False,
        })
        return vals


class HrExpenseSheet(models.Model):
    """Inherit hr.expense.sheet to add preview and download functionality"""
    _inherit = 'hr.expense.sheet'

    submitted_by_user_id = fields.Many2one('res.users', string="Submitted By", readonly=True)
    submission_date = fields.Date(string="Submission Date", readonly=True)
    approved_by_user_id = fields.Many2one('res.users', string="Approved By", readonly=True)
    paid_by_user_id = fields.Many2one('res.users', string="Paid By", readonly=True)
    payment_date = fields.Date(string="Payment Date", readonly=True)

    # Display fields with fallback logic (for reports)
    display_submitted_by = fields.Many2one(
        'res.users',
        string="Display: Submitted By",
        compute='_compute_display_fields',
        store=True,
    )
    display_submission_date = fields.Date(
        string="Display: Submission Date",
        compute='_compute_display_fields',
        store=True,
    )
    display_approved_by = fields.Many2one(
        'res.users',
        string="Display: Approved By",
        compute='_compute_display_fields',
        store=True,
    )
    display_approval_date = fields.Date(
        string="Display: Approval Date",
        compute='_compute_display_fields',
        store=True,
    )
    display_paid_by = fields.Many2one(
        'res.users',
        string="Display: Paid By",
        compute='_compute_display_fields',
        store=True,
    )
    display_payment_date = fields.Date(
        string="Display: Payment Date",
        compute='_compute_display_fields',
        store=False,
    )
    
    report_reference = fields.Char(
        string="Report ID", 
        copy=False, 
        tracking=True
    )
    
    is_report_id_editable = fields.Boolean(
        string="Is Report ID Editable",
        compute='_compute_is_report_id_editable',
        store=False,
    )
    
    def _compute_is_report_id_editable(self):
        """Report ID is editable only for saved records with empty report_reference in DB"""
        for sheet in self:
            if not sheet.id:
                # New unsaved record - not editable (will be auto-generated)
                sheet.is_report_id_editable = False
            else:
                # Check database value, not current UI value
                db_value = self.browse(sheet.id).read(['report_reference'])
                if db_value:
                    sheet.is_report_id_editable = not db_value[0].get('report_reference')
                else:
                    sheet.is_report_id_editable = True

    @api.constrains('report_reference')
    def _check_unique_report_reference(self):
        """Ensure Report ID is unique (except for empty values)"""
        for sheet in self:
            if sheet.report_reference:
                duplicate = self.search([
                    ('report_reference', '=', sheet.report_reference),
                    ('id', '!=', sheet.id),
                ], limit=1)
                if duplicate:
                    raise ValidationError(
                        f"Report ID '{sheet.report_reference}' is already used by another expense report. "
                        "Please enter a unique Report ID."
                    )

    @api.model
    def _migrate_new_report_references(self):
        """Migration: Convert old 'New' report_reference values to empty (False)"""
        old_records = self.search([('report_reference', '=', 'New')])
        if old_records:
            old_records.write({'report_reference': False})
        return True


    @api.depends(
        'submitted_by_user_id',
        'submission_date',
        'employee_id.user_id',
        'approved_by_user_id',
        'user_id',
        'approval_date',
        'paid_by_user_id',
        'payment_date',
        'account_move_ids',
        'account_move_ids.create_uid',
        'account_move_ids.state',
        'account_move_ids.write_date',
        'state',
    )
    def _compute_display_fields(self):
        """Compute display fields - only show when confident about accuracy"""
        for sheet in self:
            # Submission - show user (with fallback) but date only if explicit
            # AND only if not in draft state (unless explicitly captured)
            if sheet.submitted_by_user_id:
                sheet.display_submitted_by = sheet.submitted_by_user_id
            elif sheet.state != 'draft':
                sheet.display_submitted_by = sheet.employee_id.user_id
            else:
                sheet.display_submitted_by = False
                
            # ONLY show date if explicitly captured (no create_date fallback)
            sheet.display_submission_date = sheet.submission_date or False

            # Approval - always reliable
            # Only if approved, posted or done
            if sheet.approved_by_user_id:
                sheet.display_approved_by = sheet.approved_by_user_id
            elif sheet.state in ('approve', 'post', 'done'):
                sheet.display_approved_by = sheet.user_id or sheet.employee_id.parent_id.user_id
            else:
                sheet.display_approved_by = False
                
            sheet.display_approval_date = sheet.approval_date or False

            # -----------------------
            # Payment - only show user, never date
            # -----------------------
            paid_by = False
            
            # Only show payment info if in post or done state
            if sheet.state in ('post', 'done'):
                if sheet.paid_by_user_id:
                    # Explicitly captured (new reports)
                    paid_by = sheet.paid_by_user_id
                else:
                    # If not set, try posted moves
                    if sheet.account_move_ids:
                        posted_moves = sheet.account_move_ids.filtered(lambda m: m.state == 'posted')
                        if posted_moves:
                            # Pick the most recently posted move
                            paid_by = posted_moves.sorted('write_date')[-1].create_uid

                    # Last fallback: always employee user (only for old reports that are posted/done)
                    if not paid_by:
                        paid_by = sheet.employee_id.user_id or False

            sheet.display_paid_by = paid_by
            # Payment date: show if captured, otherwise blank
            if sheet.payment_date:
                sheet.display_payment_date = sheet.payment_date
            else:
                 sheet.display_payment_date = False

    def action_submit_sheet(self):
        """Capture who submitted and when"""
        res = super().action_submit_sheet()
        for sheet in self:
            if not sheet.submitted_by_user_id:
                sheet.sudo().write({
                    'submitted_by_user_id': self.env.user.id,
                    'submission_date': fields.Date.today(),
                })
        return res

    def action_approve_expense_sheets(self):
        """Capture who approved"""
        res = super().action_approve_expense_sheets()
        for sheet in self:
            if not sheet.approved_by_user_id:
                sheet.write({
                    'approved_by_user_id': self.env.user.id,
                })
        return res

    def action_sheet_move_create(self):
        """Capture who marked as paid (created accounting entries)"""
        res = super().action_sheet_move_create()
        for sheet in self:
            # Only set once - when accounting entries are first created
            if not sheet.paid_by_user_id:
                sheet.write({
                    'paid_by_user_id': self.env.user.id,
                    'payment_date': fields.Date.today(),
                })
        return res

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to use custom sequence for Report ID"""
        for vals in vals_list:
            if not vals.get('report_reference'):
                vals['report_reference'] = self.env['ir.sequence'].next_by_code('hr.expense.sheet.report') or False
        return super().create(vals_list)

    def action_preview_report(self):
        """
        Preview Full Expense Report (table + attachments) in browser.
        User can download from browser if needed.
        """
        self.ensure_one()
        report_id = self.report_reference if self.report_reference != 'New' else 'Draft'
        safe_name = self.name.replace('/', '-') if self.name else ''
        filename = f"Petty Cash Expenses - {self.employee_id.name} - {report_id} - {safe_name}.pdf"
        return {
            'type': 'ir.actions.act_url',
            'url': f'/my_portal/expense/preview/{self.id}/{filename}',
            'target': 'new',
        }

    def action_download_report_only(self):
        """
        Download Petty Cash Expense Summary Report (table only, no attachments).
        """
        self.ensure_one()
        report = self.env.ref('dp_portal_expense.action_report_petty_cash_expense_sheet_v2')
        return report.report_action(self)
