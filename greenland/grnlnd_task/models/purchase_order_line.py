# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, get_lang
from odoo.tools.float_utils import float_round


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.depends('product_id', 'product_qty', 'product_uom', 'order_id.partner_id')
    def _compute_price_unit_and_date_planned_and_name(self):
        """
        Compute date_planned, price_unit, and name for PO lines:
        - If vendor has supplierinfo for the product → fetch its price automatically
        - Else → use product's list_price (sale price) as default for manual entry
        """
        for line in self:
            if not line.product_id or not line.company_id:
                continue

            partner = line.order_id.partner_id
            seller = line.product_id._select_seller(
                partner_id=partner,
                quantity=line.product_qty,
                date=line.order_id.date_order and line.order_id.date_order.date() or fields.Date.context_today(line),
                uom_id=line.product_uom
            )

            if seller or not line.date_planned:
                line.date_planned = line._get_date_planned(seller).strftime(DEFAULT_SERVER_DATETIME_FORMAT)

            if seller:
                price_unit = line.env['account.tax']._fix_tax_included_price_company(
                    seller.price,
                    line.product_id.supplier_taxes_id,
                    line.taxes_id,
                    line.company_id,
                )
                price_unit = seller.currency_id._convert(
                    price_unit,
                    line.currency_id,
                    line.company_id,
                    line.order_id.date_order or fields.Date.context_today(line),
                    round=False
                )
                line.price_unit = seller.product_uom._compute_price(price_unit, line.product_uom)
            else:
                price_unit = line.product_id.lst_price
                line.price_unit = float_round(
                    price_unit,
                    precision_digits=max(
                        line.currency_id.decimal_places,
                        self.env['decimal.precision'].precision_get('Product Price')
                    )
                )

            product_ctx = {
                'partner_id': partner.id if partner else None,
                'lang': get_lang(line.env, partner.lang).code if partner else line.env.user.lang
            }
            line.name = line._get_product_purchase_description(line.product_id.with_context(product_ctx))
