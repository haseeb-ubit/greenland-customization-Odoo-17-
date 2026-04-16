from odoo import http
from odoo.http import request
import json

class DriverController(http.Controller):
    
    @http.route('/grnlnd_task/is_driver_user', type='json', auth='user')
    def is_driver_user(self):
        """Check if current user is in driver group"""
        user = request.env.user
        driver_group = request.env.ref('grnlnd_task.group_driver_access', raise_if_not_found=False)
        
        if driver_group:
            is_driver = user.has_group('grnlnd_task.group_driver_access')
            return {
                'is_driver': is_driver,
                'user_id': user.id,
                'group_id': driver_group.id if driver_group else None
            }
        return {
            'is_driver': False,
            'user_id': user.id,
            'group_id': None
        } 