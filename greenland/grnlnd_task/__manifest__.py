# -*- coding: utf-8 -*-
{
    'name': "GreenLand Customization",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "KNYSYS",
    'website': "http://knysys.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['project', 'sales_contract_and_recurring_invoices', 'account', 'l10n_sa','purchase','account_reports','product','portal'],
    'assets': {
            'web.assets_backend': [
                'grnlnd_task/static/src/js/conditional_visibility.js',
                'grnlnd_task/static/src/js/driver_search_visibility.js',
                'grnlnd_task/static/src/js/simple_driver_search_visibility.js',
                '/grnlnd_task/static/src/css/tree_view.css',
                'grnlnd_task/static/src/js/share_copy.js',
                'grnlnd_task/static/src/js/task_list_view.js',
            ],
        },
    # always loaded
    'data': [
        'views/purchase_order_template.xml',
        'security/greenland_security.xml',
        'security/ir.model.access.csv',
        #'reports/purchase_order_template.xml',
        'views/res_config_settings_views.xml',
        'views/project_task_views.xml',  # Add this line
        'views/account_move_reversal_view.xml',
        'wizard/link_invoice_wizard_view.xml',
        'views/contract_views.xml',  # New file for view inheritance
        'data/contract_data.xml',
        'data/request_update_document_template.xml',
        'data/requested_document_template.xml',
        'data/account_statement_template.xml',
        'data/payment_request_template.xml',
        'data/overdue_payment_template.xml',
        'data/invoice_service_rendered_template.xml',
        'data/contract_signature_template.xml',
        'data/sequence_data.xml',
        'views/views.xml',
        'views/templates.xml',
        'views/product_template.xml',
        'views/account_move.xml',
        'views/account_payment_views.xml',
        'views/res_partner.xml',
        'data/ir_cron_data.xml',
        'reports/service_ticket_summarry_report.xml',
        'views/service_ticket_report.xml',
        'views/service_ticket_portal_template.xml',
        'views/service_ticket_views.xml',
        'views/service_ticket_share_wizard.xml',
        'views/service_summary_report_template.xml',
        'views/service_invoice_template.xml',
        'views/sales_order.xml',
        'views/custom_header_footer.xml',
        'views/custom_invoice_portal_template.xml',
        'views/report_invoice_and_summary.xml',
        'views/custom_account_move_views.xml',
        'views/account_move_search.xml',
        'views/account_move_group_views.xml',
        'views/sale_order_quotation.xml',
        'views/terms_conditions.xml',
        'views/product_product.xml',
        'views/disposal_facilitator.xml',
        'views/vehicle.xml',
        # 'views/drivers.xml',
        'views/location.xml',
        'views/employee_hr.xml',
        'views/customer_signature_views.xml',
        #'views/purchase_order_template.xml',
        'views/purchase_order_domain.xml',
        'views/container.xml',
        'data/res_groups.xml',
        'data/ir.model.access.xml',
        'reports/report_service_summary_quotation.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'application': True,

}

