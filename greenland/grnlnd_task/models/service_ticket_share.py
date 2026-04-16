from odoo import api, fields, models, _
from odoo.exceptions import UserError
import secrets


class ProjectTask(models.Model):
    _inherit = 'project.task'

    share_token = fields.Char(copy=False, readonly=True)

    def _ensure_share_token_and_url(self):
        """Ensure token and return absolute share URL for this task."""
        self.ensure_one()
        # Optional: enforce only for digital subtype if you have such a field
        # if self.ticket_subtype != 'digital':
        #     raise UserError(_('Share is available only for digital tickets.'))

        if not self.share_token:
            # Try sequence; if not configured, fall back to a random token
            token = self.env['ir.sequence'].next_by_code('grnlnd_task.share.token')
            self.share_token = token or secrets.token_urlsafe(16)

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/grnlnd/service_ticket/share/{self.id}/{self.share_token}"

    def action_generate_share_link(self):
        """Open a modal wizard showing the shareable link with copy button."""
        self.ensure_one()
        url = self._ensure_share_token_and_url()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'service.ticket.share.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_link': url,
                'default_task_id': self.id,
            },
        }


class ServiceTicketShareWizard(models.TransientModel):
    _name = 'service.ticket.share.wizard'
    _description = 'Service Ticket Share Wizard'

    task_id = fields.Many2one('project.task', readonly=True)
    link = fields.Char(readonly=True)

    def action_copy_link(self):
        self.ensure_one()
        # Client JS copies from the field; we just show a toast
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Share'),
                'message': _('Link copied to clipboard.'),
                'type': 'success',
                'sticky': False,
            }
        }

