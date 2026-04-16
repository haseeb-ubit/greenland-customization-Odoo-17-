# -*- coding: utf-8 -*-
# from odoo import http


# class GrnlndTask(http.Controller):
#     @http.route('/grnlnd_task/grnlnd_task', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/grnlnd_task/grnlnd_task/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('grnlnd_task.listing', {
#             'root': '/grnlnd_task/grnlnd_task',
#             'objects': http.request.env['grnlnd_task.grnlnd_task'].search([]),
#         })

#     @http.route('/grnlnd_task/grnlnd_task/objects/<model("grnlnd_task.grnlnd_task"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('grnlnd_task.object', {
#             'object': obj
#         })

