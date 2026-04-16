{
    'name': 'Document Expiry Report',
    'version': '1.0',
    'category': 'Reporting',
    'summary': 'Generate reports for document expiration dates',
    'description': """
        This module adds a report generator for document expiration dates.
        Features:
        - Custom date range selection
        - PDF report generation
        - Document expiration tracking
    """,
    'depends': ['base', 'web', 'grnlnd_task'],
    'data': [
        'security/ir.model.access.csv',
        'wizards/expiry_report_wizard_view.xml',
        'reports/document_expiry_report.xml',
        'views/menu_items.xml',
        'data/cron_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
} 