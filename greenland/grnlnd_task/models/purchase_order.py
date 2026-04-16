from odoo import models, api, fields, _
from odoo.exceptions import UserError
import num2words

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        required=True,
        domain="[('x_studio_contact_type', '=', 'Vendor')]",
        change_default=True,
        tracking=True,
        check_company=True,
        help="Only vendors will appear in this list."
    )

    allowed_product_ids = fields.Many2many(
        'product.product',
        compute='_compute_allowed_products',
        string='Allowed Products',
        store=False
    )

    @api.depends('partner_id')
    def _compute_allowed_products(self):
        """Allow all purchasable products for any vendor."""
        Product = self.env['product.product']

        for order in self:
            purchasable_products = Product.search([('purchase_ok', '=', True)])
            order.allowed_product_ids = [(6, 0, purchasable_products.ids)]

    def amount_in_words(self):
        """Convert PO total amount to words (English)."""
        for order in self:
            whole_number = int(order.amount_total)
            fractional_number = round((order.amount_total - whole_number) * 100)

            whole_in_words = num2words.num2words(whole_number, lang='en')
            fractional_in_words = num2words.num2words(fractional_number, lang='en')

            return f"{whole_in_words.title()} Riyals and {fractional_in_words.title()} Halalas"

    def amount_in_words_ar(self):
        """Convert PO total amount to words (Arabic)."""
        for order in self:
            whole_number = int(order.amount_total)
            fractional_number = round((order.amount_total - whole_number) * 100)

            whole_in_words = num2words.num2words(whole_number, lang='ar')
            fractional_in_words = num2words.num2words(fractional_number, lang='ar')

            return f"{whole_in_words} ريال و {fractional_in_words} هللة"

    def button_confirm(self):
        """Override to block confirmation when no product lines have been added."""
        for order in self:
            real_lines = order.order_line.filtered(lambda l: not l.display_type)
            if not real_lines:
                raise UserError(_(
                    'You cannot confirm a Purchase Order with no products. '
                    'Please add at least one product line before confirming.'
                ))
        return super().button_confirm()

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override to block creation of a PO that has no product lines.
        This prevents an empty record (and its auto-generated sequence number)
        from being saved at all — even on manual save or chatter auto-save.
        """
        for vals in vals_list:
            lines = vals.get('order_line', [])
            # Each line is a Command tuple: (0, 0, {...}) for a new line.
            # Filter out section/note lines (display_type is set) and pure deletes.
            real_lines = [
                cmd for cmd in lines
                if isinstance(cmd, (list, tuple))
                and cmd[0] == 0
                and not cmd[2].get('display_type')
            ]
            if not real_lines:
                raise UserError(_(
                    'You cannot save a Purchase Order with no products. '
                    'Please add at least one product line.'
                ))
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if 'order_line' in vals:
            for order in self:
                real_lines = order.order_line.filtered(lambda l: not l.display_type)
                if not real_lines:
                    raise UserError(_(
                        'You cannot save a Purchase Order with no products. '
                        'Please add at least one product line.'
                    ))
        return res

    def _add_supplier_to_product(self):
        """
        Override to prevent auto-creation of vendor pricelist entries on PO confirm.
        """
        return
    @api.onchange('partner_id')
    def _onchange_partner_id_clear_lines(self):
        """Clear order lines when vendor changes to prevent mismatched products."""
        if self.partner_id:
            self.order_line = [(5, 0, 0)]


from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # Ensure these fields are still there
    comments = fields.Text(string='Comments')
    comment_date = fields.Date(string='Comment Date')

    def action_print_custom_report(self):
        """ This method is triggered by the 'Report' button in the list view """
        if not self:
            raise UserError(_("Please select at least one Purchase Order to print!"))

        # This triggers the PDF report you defined in XML
        return self.env.ref('grnlnd_task.action_report_purchase_order_with_comments').report_action(self)

from odoo import models, api

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def action_print_purchase_reports(self):
        # 'self' contains all the records you selected in the list view
        # We trigger the standard Purchase Order report
        return self.env.ref('purchase.action_report_purchase_order').report_action(self)