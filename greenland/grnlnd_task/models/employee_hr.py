from odoo import fields, models, api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    hourly_cost = fields.Monetary('Hourly Cost', currency_field='currency_id',
        groups="hr.group_hr_user", default=0.0)

    _sql_constraints = [
        ('identification_id_unique', 'unique(identification_id)', 'The Employee ID must be unique!')
    ]

    identification_id = fields.Char(string='Identification No', tracking=True, copy=False)

    @api.model
    def create(self, vals):
        # Auto-generate employee ID if not provided
        if not vals.get('identification_id'):
            vals['identification_id'] = self.env['ir.sequence'].next_by_code('hr.employee.identification') or False
        
        employee = super().create(vals)
        employee._sync_access_groups()
        return employee

    def write(self, vals):
        # Only prevent changing identification_id if it's already set
        if 'identification_id' in vals:
            for employee in self:
                if employee.identification_id and vals.get('identification_id') != employee.identification_id:
                    # Don't allow changing existing ID, but allow setting empty to a value
                    del vals['identification_id']
                    break
        
        res = super().write(vals)
        self._sync_access_groups()
        return res

    def _sync_access_groups(self):
        driver_group = self.env.ref('grnlnd_task.group_driver_access')
        dispatcher_group = self.env.ref('grnlnd_task.group_dispatcher_access')
        for employee in self:
            user = employee.user_id
            if user:
                if employee.job_id.name == 'Driver':
                    user.write({'groups_id': [(4, driver_group.id), (3, dispatcher_group.id)]})
                elif employee.job_id.name == 'Dispatcher':
                    user.write({'groups_id': [(4, dispatcher_group.id), (3, driver_group.id)]})
                else:
                    user.write({'groups_id': [(3, driver_group.id), (3, dispatcher_group.id)]})