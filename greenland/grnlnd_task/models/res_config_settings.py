from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # These store the values globally in Odoo
    silver_threshold = fields.Float(string="Silver Max Range", config_parameter='grnlnd.silver_threshold')
    gold_threshold = fields.Float(string="Gold Max Range", config_parameter='grnlnd.gold_threshold')
    platinum_threshold = fields.Float(string="Platinum Min Range", config_parameter='grnlnd.platinum_threshold')

