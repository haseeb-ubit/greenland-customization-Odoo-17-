# -*- coding: utf-8 -*-
##############################################################################
#
#
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
{
    'name': 'Sales Contract and Recurring Invoices',
    'version': '17.0.1.0.0',
    'category': 'Sales,Accounting',
    'summary': """Create sale contracts and recurring invoices.""",
    'description': """This module helps to create sale contracts with recurring 
    invoices and enable to access all sale contracts from website portal.""",
    'author': '',
    'company': '',
    'maintainer': '',
    'website': 'https://www.example.com',
    'depends': ['sale_management'],
    'data': [
        'security/subscription_contracts_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'report/subscription_contract_reports.xml',
        'views/subscription_contracts_views.xml',
        'views/subscription_contracts_cancel_wizard.xml',
        'views/account_move_views.xml',
        # 'views/subscription_contracts_templates.xml',
        'report/subscription_contract_templates.xml',
        
    ],
    'images': ['static/description/banner.png'],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
