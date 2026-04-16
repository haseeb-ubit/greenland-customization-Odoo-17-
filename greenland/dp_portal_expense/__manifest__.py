# -*- coding: utf-8 -*-
# DP InfoSol PVT LTD. See LICENSE file for full copyright and licensing details.
{
    'name'       : 'Employee portal expense',
    'version'    : '17.0',
    "author"     : "DP InfoSOl",
    "support"    : "help.dpinfosol@gmail.com",
    'category'   : 'HR',
    'summary'    : '''This app helpful to allow employees to create expense from portal.''',
    'description': """ employees to record expense from portal create expense delete expense and update expense.
    """,
    'depends'    : ['base','hr','hr_expense','portal'],
    'data'       : [
                    'data/ir_sequence.xml',
                    'data/migrate_report_ids.xml',
                    'report/expense_report_actions.xml',
                    'views/expense_data.xml',
                    'views/hr_view.xml',
                    'views/hr_expense_views.xml',
                    'report/expense_footer_layout.xml',
                    'report/expense_report_templates.xml',
                    'report/expense_report_with_invoices.xml',
                   ],
    'installable' : True,
    'auto_install': False,
    'price'       : 30,
    'assets'      :{
                    'web.assets_frontend': ['dp_portal_expense/static/src/js/create_expense.js',],
                    'web.assets_backend': [
                        'dp_portal_expense/static/src/js/vat_lookup_widget.js',
                        'dp_portal_expense/static/src/xml/vat_lookup_widget.xml',
                    ],
                   },
    'currency'    : "EUR",
    'images'      : ["static/description/banner.jpg",],
}

