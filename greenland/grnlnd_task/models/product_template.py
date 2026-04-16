# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'
    _rec_names_search = ['name', 'default_code']

    name_ar = fields.Char(string="Product Name (Arabic)")
    non_hazardous = fields.Boolean('Non-Hazardous', default=False)
    hazardous = fields.Boolean('Hazardous', default=False)

class ProductProduct(models.Model):
    _inherit = 'product.product'
    _rec_names_search = ['name', 'default_code', 'barcode']

    name_ar = fields.Char(string="Product Name (Arabic)")