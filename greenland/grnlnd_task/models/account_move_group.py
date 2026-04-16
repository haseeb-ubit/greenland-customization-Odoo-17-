# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountMoveGroup(models.Model):
    _name = 'account.move.group'
    _description = 'Journal Entry Group'
    _order = 'partner_id, journal_id'

    name = fields.Char(
        string='Group Name',
        compute='_compute_name',
        store=True,
        readonly=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner/Employee',
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
        help='Partner for whom these journal entries are grouped'
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
        help='Journal for these grouped entries'
    )
    move_ids = fields.One2many(
        'account.move',
        'group_id',
        string='Journal Entries',
        help='Journal entries in this group'
    )
    entry_count = fields.Integer(
        string='Entry Count',
        compute='_compute_entry_count',
        store=True
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('active', 'Active')],
        string='Status',
        default='draft',
        help='Draft: No entries yet, Active: Has entries'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    
    # Computed field to show all journal lines from all entries
    all_line_ids = fields.One2many(
        'account.move.line',
        compute='_compute_all_line_ids',
        string='All Journal Items',
        help='All journal items from all entries in this group'
    )
    
    @api.depends('move_ids', 'move_ids.line_ids')
    def _compute_all_line_ids(self):
        """Compute all journal lines from all entries in the group"""
        for group in self:
            group.all_line_ids = group.move_ids.mapped('line_ids')
    
    total_debit = fields.Monetary(
        string='Total Debit',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id'
    )
    total_credit = fields.Monetary(
        string='Total Credit',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id'
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        string='Currency'
    )
    total_entries_amount = fields.Monetary(
        string='Total Entries Amount',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id'
    )
    
    @api.depends('move_ids', 'move_ids.line_ids', 'move_ids.line_ids.debit', 'move_ids.line_ids.credit', 'move_ids.amount_total')
    def _compute_totals(self):
        """Compute total debit and credit from all journal lines"""
        for group in self:
            lines = group.move_ids.mapped('line_ids')
            group.total_debit = sum(lines.mapped('debit'))
            group.total_credit = sum(lines.mapped('credit'))
            group.total_entries_amount = sum(group.move_ids.mapped('amount_total'))

    @api.depends('partner_id', 'journal_id')
    def _compute_name(self):
        """Compute group name from partner and journal"""
        for group in self:
            if group.partner_id and group.journal_id:
                group.name = f"{group.partner_id.name} - {group.journal_id.name}"
            else:
                group.name = _('New Group')

    @api.depends('move_ids')
    def _compute_entry_count(self):
        """Compute count of journal entries in group"""
        for group in self:
            group.entry_count = len(group.move_ids)

    @api.model
    def create(self, vals):
        """Override create to set state to active if moves are provided"""
        group = super(AccountMoveGroup, self).create(vals)
        if group.move_ids:
            group.state = 'active'
        return group

    def write(self, vals):
        """Override write to update state when entries are added"""
        res = super(AccountMoveGroup, self).write(vals)
        for group in self:
            if group.move_ids and group.state == 'draft':
                group.state = 'active'
        return res

    def action_view_entries(self):
        """Open tree view of journal entries in this group"""
        self.ensure_one()
        return {
            'name': _('Journal Entries: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.move_ids.ids)],
            'context': {
                'default_group_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_journal_id': self.journal_id.id,
            }
        }

    def action_create_entry(self):
        """Create a new journal entry in this group"""
        self.ensure_one()
        
        # Get the next sequence in group
        max_sequence = 0
        if self.move_ids:
            max_sequence = max(self.move_ids.mapped('sequence_in_group') or [0])
        
        return {
            'name': _('New Journal Entry'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_move_type': 'entry',
                'default_group_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_journal_id': self.journal_id.id,
                'default_sequence_in_group': max_sequence + 1,
            }
        }
    
    def action_view_all_lines(self):
        """Open all journal items in a tree view grouped by entry"""
        self.ensure_one()
        line_ids = self.move_ids.mapped('line_ids').ids
        # Get company currency for context
        company_currency = self.company_id.currency_id
        return {
            'name': _('Journal Items - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'tree',
            'view_id': self.env.ref('grnlnd_task.view_account_move_line_grouped_tree').id,
            'domain': [('id', 'in', line_ids)],
            'context': {
                'group_by': 'move_id',
                'expand': True,
                'default_company_currency_id': company_currency.id if company_currency else False,
            },
            'target': 'current',
        }

    @api.model
    def find_or_create_group(self, partner_id, journal_id):
        """Find existing group or create new one for partner and journal"""
        group = self.search([
            ('partner_id', '=', partner_id),
            ('journal_id', '=', journal_id),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        
        if not group:
            group = self.create({
                'partner_id': partner_id,
                'journal_id': journal_id,
            })
        
        return group
