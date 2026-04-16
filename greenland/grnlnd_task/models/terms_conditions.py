# -*- coding: utf-8 -*-


from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError, AccessError



class TermsAndConditions(models.Model):
    _name = 'terms_and_conditions'
    _description = 'Terms and Conditions'

    name = fields.Char("Term Code")
    # category = fields.Char("Category")
    category = fields.Many2one('terms.category', string="Category", required=True)
    note = fields.Html(
        string="Terms and conditions")


class TermsCategory(models.Model):
    _name = 'terms.category'
    _description = 'Terms and Conditions Category'

    name = fields.Char("Category Name", required=True)
    terms_count = fields.Integer(compute='_compute_terms_count')

    @api.depends('name')
    def _compute_terms_count(self):
        for category in self:
            category.terms_count = self.env['terms_and_conditions'].search_count([('category', '=', category.id)])
