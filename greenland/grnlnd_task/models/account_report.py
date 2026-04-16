import base64
import io
import markupsafe ,textwrap ,math
from odoo.modules.module import get_module_resource
from odoo import models, fields, api, _, osv, _lt
from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.tools import config, date_utils, get_lang, float_compare, float_is_zero
from odoo.tools.float_utils import float_round
from odoo.tools.misc import formatLang, format_date, xlsxwriter
from odoo.tools.safe_eval import expr_eval, safe_eval
from odoo.models import check_method_name
from itertools import groupby
import logging

_logger = logging.getLogger(__name__)


class AccountReport(models.Model):
    _inherit = 'account.report'

    # def export_to_pdf(self, options):
    #     self.ensure_one()

    #     base_url = self.env['ir.config_parameter'].sudo().get_param('report.url') or self.env[
    #         'ir.config_parameter'].sudo().get_param('web.base.url')
    #     rcontext = {
    #         'mode': 'print',
    #         'base_url': base_url,
    #         'company': self.env.company,
    #     }

    #     print_options = self.get_options(previous_options={**options, 'export_mode': 'print'})
    #     if print_options['sections']:
    #         reports_to_print = self.env['account.report'].browse(
    #             [section['id'] for section in print_options['sections']])
    #     else:
    #         reports_to_print = self

    #     reports_options = []
    #     for report in reports_to_print:
    #         reports_options.append(
    #             report.get_options(previous_options={**print_options, 'selected_section_id': report.id}))

    #     grouped_reports_by_format = groupby(
    #         zip(reports_to_print, reports_options),
    #         key=lambda report: len(report[1]['columns']) > 5
    #     )

    #     footer = self.env['ir.actions.report']._render_template("web.external_layout", values=rcontext)
    #     footer = self.env['ir.actions.report']._render_template("web.minimal_layout", values=dict(rcontext, subst=True,
    #                                                                                               body=markupsafe.Markup(
    #                                                                                                   footer.decode())))

    #     action_report = self.env['ir.actions.report']
    #     files_stream = []
    #     for is_landscape, reports_with_options in grouped_reports_by_format:
    #         bodies = []

    #         for report, report_options in reports_with_options:
    #             bodies.append(report._get_pdf_export_html(
    #                 report_options,
    #                 report._filter_out_folded_children(report._get_lines(report_options)),
    #                 additional_context={'base_url': base_url}
    #             ))

    #         files_stream.append(
    #             io.BytesIO(action_report._run_wkhtmltopdf(
    #                 bodies,
    #                 footer=footer.decode(),
    #                 landscape=is_landscape or self._context.get('force_landscape_printing'),
    #                 specific_paperformat_args={
    #                     'data-report-margin-top': 10,
    #                     'data-report-header-spacing': 10,
    #                     'data-report-margin-bottom': 15,
    #                 }
    #             )
    #             ))

    #     if len(files_stream) > 1:
    #         result_stream = action_report._merge_pdfs(files_stream)
    #         result = result_stream.getvalue()
    #         # Close the different stream
    #         result_stream.close()
    #         for file_stream in files_stream:
    #             file_stream.close()
    #     else:
    #         result = files_stream[0].read()

    #     return {
    #         'file_name': self.get_default_report_filename(options, 'pdf'),
    #         'file_content': result,
    #         'file_type': 'pdf',
    #     }

    def _inject_report_into_xlsx_sheet(self, options, workbook, sheet):
        # ================================
        # HEADER
        # ================================
        header_img_path = get_module_resource('grnlnd_task', 'static/src/img', 'invoice_header.png')
        header_height = 5
        if header_img_path:
            sheet.insert_image('A1', header_img_path, {
                'x_scale': 0.910,
                'y_scale': 1.1,
                'x_offset': 3,
                'y_offset': 2
            })

        y_offset = header_height +1
        
        # ================================
        # STYLES
        # ================================
        customer_label_style = workbook.add_format({
            'font_name': 'Arial',
            'font_size': 10,
            'bold': True,
            'font_color': '#000000'
        })
        customer_value_style = workbook.add_format({
            'font_name': 'Arial',
            'font_size': 10,
            'font_color': '#000000'
        })
        title_red_style = workbook.add_format({
            'font_name': 'Arial',
            'font_size': 14,
            'bold': True,
            'font_color': '#FF0000'
        })
        date_range_style = workbook.add_format({
            'font_name': 'Arial',
            'font_size': 10,
            'font_color': '#FF0000',
            'bold': True
        })
        balance_label_style = workbook.add_format({
            'font_name': 'Arial',
            'font_size': 10,
            'bold': True,
            'font_color': '#000000',
            'align': 'right'
        })
        balance_value_style = workbook.add_format({
            'font_name': 'Arial',
            'font_size': 10,
            'font_color': '#000000',
            'align': 'right',
            'num_format': '#,##0.00 "SAR"'
        })

        date_from_raw = options.get('date', {}).get('date_from', '')
        date_to_raw = options.get('date', {}).get('date_to', '')

        def format_date_to_dd_mmm_yyyy(date_str):
            if not date_str:
                return ''
            try:
                from datetime import datetime
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%-d/%b/%Y')
                parts = formatted_date.split('/')
                if len(parts) == 3:
                    parts[1] = parts[1].capitalize()  
                    return '/'.join(parts)
                return formatted_date
            except:
                return date_str

        date_from = format_date_to_dd_mmm_yyyy(date_from_raw)
        date_to = format_date_to_dd_mmm_yyyy(date_to_raw)

        # ================================
        # BODY
        # ================================
        print_mode_self = self.with_context(no_format=True)
        lines = self._filter_out_folded_children(print_mode_self._get_lines(options))

        partners_data = {}
        # Track rows where A:B are already merged to avoid duplicate merge errors
        merged_rows_ab = set()
        total_initial_balance = 0.0
        total_debit = 0.0
        total_credit = 0.0

        partner_handler = self.env['account.partner.ledger.report.handler']



        for line in lines:
            line_model, line_id = self._get_model_info_from_id(line['id'])

            if line_model == 'res.partner' and line_id:
                partner = self.env['res.partner'].browse(line_id)
                if partner:
                    partner_initial_balance = 0.0
                    partner_debit = 0.0
                    partner_credit = 0.0
                    if line.get('columns'):
                        for col in line['columns']:
                            if isinstance(col, dict):
                                col_value = col.get('no_format', 0)
                                expression_label = col.get('expression_label', '')

                                if expression_label == 'debit':
                                    partner_debit = float(col_value) if col_value else 0.0
                                elif expression_label == 'credit':
                                    partner_credit = float(col_value) if col_value else 0.0
                                elif expression_label == 'balance':
                                    partner_initial_balance = float(
                                        col_value) - partner_debit + partner_credit if col_value else 0.0

                    if partner_initial_balance == 0.0 and partner_debit == 0.0 and partner_credit == 0.0:
                        try:
                            initial_balances = partner_handler._get_initial_balance_values([partner.id], options)
                            if partner.id in initial_balances:
                                for col_group_key, balance_data in initial_balances[partner.id].items():
                                    partner_initial_balance = balance_data.get('balance', 0.0)
                                    break
                        except Exception as e:
                            _logger.warning(f"Could not get initial balance for partner {partner.id}: {e}")
                            partner_initial_balance = 0.0

                    partner_closing_balance = partner_initial_balance + partner_debit - partner_credit

                    partners_data[partner.id] = {
                        'partner': partner,
                        'initial_balance': partner_initial_balance,
                        'debit': partner_debit,
                        'credit': partner_credit,
                        'closing_balance': partner_closing_balance
                    }



                    total_initial_balance += partner_initial_balance
                    total_debit += partner_debit
                    total_credit += partner_credit


            # REMOVED: Don't use the report's total line as it includes filtered invoices
            # We calculate totals from individual partner lines instead
            # elif line.get('id') and 'total' in str(line.get('id', '')):
            #     if line.get('columns'):
            #         for col in line['columns']:
            #             if isinstance(col, dict):
            #                 col_value = col.get('no_format', 0)
            #                 expression_label = col.get('expression_label', '')
            #
            #                 if expression_label == 'debit':
            #                     total_debit = float(col_value) if col_value else 0.0
            #                 elif expression_label == 'credit':
            #                     total_credit = float(col_value) if col_value else 0.0

        total_closing_balance = total_initial_balance + total_debit - total_credit



        # ================================
        # STATEMENT OF ACCOUNT header + date range always, totals only if multiple customers
        # ================================
        if partners_data:
            statement_row = y_offset
            sheet.merge_range(statement_row, 0, statement_row, 3, 'Statement Of Account', title_red_style)
            y_offset += 2

            sheet.merge_range(y_offset, 0, y_offset, 1, f'From {date_from} To {date_to}', date_range_style)
            merged_rows_ab.add(y_offset)
            y_offset += 2

            if len(partners_data) > 1:
                balance_row = y_offset -4
                sheet.write(balance_row, 5, 'Opening Balance:', balance_label_style)
                sheet.write(balance_row, 6, total_initial_balance, balance_value_style)
                balance_row += 1

                sheet.write(balance_row, 5, 'Total Debits:', balance_label_style)
                sheet.write(balance_row, 6, total_debit, balance_value_style)
                balance_row += 1

                sheet.write(balance_row, 5, 'Total Credits:', balance_label_style)
                sheet.write(balance_row, 6, total_credit, balance_value_style)
                balance_row += 1

                sheet.write(balance_row, 5, 'Closing Balance:', balance_label_style)
                sheet.write(balance_row, 6, total_closing_balance, balance_value_style)
                y_offset = balance_row + 3

        # ================================
        # CUSTOMER DETAILS
        # ================================
        if not partners_data:
            _logger.warning("No partners found in the report lines. This might indicate an issue with the report data.")
            sheet.merge_range(y_offset, 0, y_offset, 1, 'No customer data found in the selected period.', customer_value_style)
            merged_rows_ab.add(y_offset)
            y_offset += 2

        for partner_id, partner_data in partners_data.items():
            partner = partner_data['partner']

            sheet.merge_range(y_offset, 0, y_offset, 1, 'Customer Details:', customer_label_style)
            merged_rows_ab.add(y_offset)
            sheet.write(y_offset, 5, 'Opening Balance:', balance_label_style)
            sheet.write(y_offset, 6, partner_data['initial_balance'], balance_value_style)
            y_offset += 1

            sheet.merge_range(y_offset, 0, y_offset, 1, f'Customer Name: {partner.name}', customer_value_style)
            merged_rows_ab.add(y_offset)
            sheet.write(y_offset, 5, 'Total Debits:', balance_label_style)
            sheet.write(y_offset, 6, partner_data['debit'], balance_value_style)
            y_offset += 1

            company_registry = partner.company_registry if partner.company_registry else ''
            sheet.merge_range(y_offset, 0, y_offset, 1, f'Customer CR #: {company_registry}', customer_value_style)
            merged_rows_ab.add(y_offset)
            sheet.write(y_offset, 5, 'Total Credits:', balance_label_style)
            sheet.write(y_offset, 6, partner_data['credit'], balance_value_style)
            y_offset += 1

            customer_vat = partner.vat if partner.vat else ''
            sheet.merge_range(y_offset, 0, y_offset, 1, f'Customer VAT #: {customer_vat}', customer_value_style)
            merged_rows_ab.add(y_offset)
            sheet.write(y_offset, 5, 'Closing Balance:', balance_label_style)
            sheet.write(y_offset, 6, partner_data['closing_balance'], balance_value_style)
            y_offset += 2

        # ================================
        # REPORT TABLE
        # ================================
        def write_with_colspan(sheet, x, y, value, colspan, style):
            if colspan == 1:
                sheet.write(y, x, value, style)
            else:
                sheet.merge_range(y, x, y, x + colspan - 1, value, style)

        def wrap_text_dynamically(text, max_line_length=60):
            if not text:
                return ""
            if not isinstance(text, str):
                text = str(text)
            return textwrap.fill(text, width=max_line_length)

        def calculate_row_height_dynamic(text, font_size=11, col_width=50):
            if not text or not isinstance(text, str):
                return 15

            avg_char_width = 0.6
            effective_width = col_width / avg_char_width
            chars_per_line = max(1, int(effective_width))
            num_lines = math.ceil(len(text) / chars_per_line)
            num_lines = text.count("\n") + num_lines
            base_height = 15
            line_height = font_size * 1.35
            total_height = base_height + (num_lines - 1) * line_height
            return max(15, min(total_height, 250))

        date_default_col1_style = workbook.add_format(
            {'font_name': 'Arial', 'font_size': 11, 'font_color': '#000000', 'indent': 2, 'num_format': 'd/mmm/yyyy', 'align': 'center', 'valign': 'vcenter'})
        date_default_style = workbook.add_format(
            {'font_name': 'Arial', 'font_size': 11, 'font_color': '#000000', 'num_format': 'd/mmm/yyyy', 'align': 'center', 'valign': 'vcenter'})
        default_col1_style = workbook.add_format(
            {'font_name': 'Arial', 'font_size': 11, 'font_color': '#000000', 'indent': 2, 'text_wrap': True, 'align': 'center', 'valign': 'vcenter'})
        default_style = workbook.add_format({'font_name': 'Arial', 'font_size': 11, 'font_color': '#000000', 'align': 'center', 'valign': 'vcenter'})
        # Currency format style for debit, credit, and balance columns
        currency_style = workbook.add_format({
            'font_name': 'Arial', 'font_size': 11, 'font_color': '#000000',
            'num_format': '#,##0.00 "SAR"', 'valign': 'vcenter'
        })
        currency_bold_style = workbook.add_format({
            'font_name': 'Arial', 'font_size': 11, 'font_color': '#000000', 'bold': True,
            'num_format': '#,##0.00 "SAR"', 'valign': 'vcenter'
        })
        # Currency styles with bottom borders for level 0 and 1 rows
        currency_bold_level0_style = workbook.add_format({
            'font_name': 'Arial', 'font_size': 11, 'font_color': '#000000', 'bold': True,
            'num_format': '#,##0.00 "SAR"', 'bottom': 6, 'valign': 'vcenter'
        })
        currency_bold_level1_style = workbook.add_format({
            'font_name': 'Arial', 'font_size': 11, 'font_color': '#000000', 'bold': True,
            'num_format': '#,##0.00 "SAR"', 'bottom': 1, 'valign': 'vcenter'
        })
        title_style = workbook.add_format({'font_name': 'Arial', 'bold': True, 'bottom': 1, 'align': 'center', 'valign': 'vcenter'})
        level_0_style = workbook.add_format(
            {'font_name': 'Arial', 'bold': True, 'font_size': 11, 'bottom': 6, 'font_color': '#000000'})
        level_1_style = workbook.add_format(
            {'font_name': 'Arial', 'bold': True, 'font_size': 11, 'bottom': 1, 'font_color': '#000000'})
        level_2_col1_style = workbook.add_format(
            {'font_name': 'Arial', 'bold': True, 'font_size': 11, 'font_color': '#000000', 'indent': 1,
             'text_wrap': True, 'align': 'center', 'valign': 'vcenter'})
        level_2_col1_total_style = workbook.add_format(
            {'font_name': 'Arial', 'bold': True, 'font_size': 11, 'font_color': '#000000', 'text_wrap': True, 'align': 'center', 'valign': 'vcenter'})
        level_2_style = workbook.add_format(
            {'font_name': 'Arial', 'bold': True, 'font_size': 11, 'font_color': '#000000', 'align': 'center', 'valign': 'vcenter'})
        level_3_col1_style = workbook.add_format(
            {'font_name': 'Arial', 'font_size': 11, 'font_color': '#000000', 'indent': 2, 'text_wrap': True, 'align': 'center', 'valign': 'vcenter'})
        level_3_col1_total_style = workbook.add_format(
            {'font_name': 'Arial', 'bold': True, 'font_size': 11, 'font_color': '#000000', 'indent': 1,
             'text_wrap': True, 'align': 'center', 'valign': 'vcenter'})
        level_3_style = workbook.add_format({'font_name': 'Arial', 'font_size': 11, 'font_color': '#000000', 'align': 'center', 'valign': 'vcenter'})

        account_lines_split_names = {}
        for line in lines:
            line_model = self._get_model_info_from_id(line['id'])[0]
            if line_model == 'account.account':
                account_lines_split_names[line['id']] = self.env['account.account']._split_code_name(line['name'])

        if len(account_lines_split_names) > 0:
            sheet.set_column(0, 0, 11)
            sheet.set_column(1, 1, 50)
        else:
            sheet.set_column(0, 0, 50)

        sheet.set_column(1, 1, 5)
        original_x_offset = 1 if len(account_lines_split_names) > 0 else 0
        x_offset = original_x_offset + 1

        unwanted_columns = ['journal', 'account', 'matching', 'amount_currency', 'journal_id', 'account_id',
                            'matching_number']
        filtered_columns = []
        filtered_column_headers = []

        for column in options['columns']:
            column_name = column.get('name', '').lower()
            expression_label = column.get('expression_label', '').lower()
            skip_column = False
            for unwanted in unwanted_columns:
                if unwanted in column_name or unwanted in expression_label:
                    skip_column = True
                    break
            if not skip_column:
                filtered_columns.append(column)

        for header_level in filtered_column_headers:
            for header in header_level:
                ...
            y_offset += 1

        header_style = workbook.add_format({'bold': True, 'font_name': 'Arial', 'font_size': 12})

        for header_level in filtered_column_headers:
            for header in header_level:
                colspan = header.get('colspan', 1)
                write_with_colspan(sheet, x_offset + 1, y_offset, header.get('name', ''), colspan, header_style)
                x_offset += colspan
            y_offset += 1
            x_offset = original_x_offset + 1

        for column in filtered_columns:
            colspan = column.get('colspan', 1)
            # Check if this is a currency column header
            expression_label = column.get('expression_label', '').lower()
            if expression_label in ['debit', 'credit', 'balance']:
                # Create a title style with currency format
                currency_title_style = workbook.add_format({
                    'font_name': 'Arial', 'bold': True, 'bottom': 1,
                    'num_format': '#,##0.00 "SAR"', 'align': 'center', 'valign': 'vcenter'
                })
                write_with_colspan(sheet, x_offset + 1, y_offset, column.get('name', ''), colspan, currency_title_style)
            else:
                write_with_colspan(sheet, x_offset + 1, y_offset, column.get('name', ''), colspan, title_style)
            x_offset += colspan
        y_offset += 1



        if options.get('order_column'):
            lines = self.sort_lines(lines, options)

        for y in range(0, len(lines)):
            level = lines[y].get('level')
            if lines[y].get('caret_options'):
                style = level_3_style
                col1_style = level_3_col1_style
            elif level == 0:
                y_offset += 1
                style = level_0_style
                col1_style = style
            elif level == 1:
                style = level_1_style
                col1_style = style
            elif level == 2:
                style = level_2_style
                col1_style = 'total' in lines[y].get('class', '').split(
                    ' ') and level_2_col1_total_style or level_2_col1_style
            elif level == 3:
                style = level_3_style
                col1_style = 'total' in lines[y].get('class', '').split(
                    ' ') and level_3_col1_total_style or level_3_col1_style
            else:
                style = default_style
                col1_style = default_col1_style

            x_offset = original_x_offset + 1
            if lines[y]['id'] in account_lines_split_names:
                code, name = account_lines_split_names[lines[y]['id']]
                sheet.write(y + y_offset, x_offset - 2, code, col1_style)
                if x_offset == 1:
                    wrapped_value = wrap_text_dynamically(cell_value, max_line_length=60)
                    # Merge A:B for first column
                    sheet.merge_range(y + y_offset, x_offset - 1, y + y_offset, x_offset, wrapped_value, col1_style)
                    merged_rows_ab.add(y + y_offset)
                    required_height = calculate_row_height_dynamic(wrapped_value, font_size=11, col_width=50)
                    sheet.set_row(y + y_offset, required_height)
                else:
                    sheet.write(y + y_offset, x_offset - 1, name, col1_style)
            else:
                if lines[y].get('parent_id') and lines[y]['parent_id'] in account_lines_split_names:
                    sheet.write(y + y_offset, x_offset - 2, account_lines_split_names[lines[y]['parent_id']][0],
                                col1_style)
                cell_type, cell_value = self._get_cell_type_value(lines[y])
                if cell_type == 'date':
                    from datetime import datetime
                    if isinstance(cell_value, str):
                        try:
                            date_obj = datetime.strptime(cell_value, '%Y-%m-%d')
                            # Merge A:B; write formatted string to merged cell to avoid Excel date constraints
                            date_text = date_obj.strftime('%d/%b/%Y')
                            sheet.merge_range(y + y_offset, x_offset - 1, y + y_offset, x_offset, date_text, date_default_col1_style)
                            merged_rows_ab.add(y + y_offset)
                        except:
                            sheet.merge_range(y + y_offset, x_offset - 1, y + y_offset, x_offset, str(cell_value), date_default_col1_style)
                            merged_rows_ab.add(y + y_offset)
                    else:
                        try:
                            date_text = cell_value.strftime('%d/%b/%Y')
                        except Exception:
                            date_text = str(cell_value)
                        sheet.merge_range(y + y_offset, x_offset - 1, y + y_offset, x_offset, date_text, date_default_col1_style)
                        merged_rows_ab.add(y + y_offset)
                else:
                    if x_offset == 1:
                        wrapped_value = wrap_text_dynamically(cell_value, max_line_length=60)
                        # Merge A:B for first column
                        sheet.merge_range(y + y_offset, x_offset - 1, y + y_offset, x_offset, wrapped_value, col1_style)
                        merged_rows_ab.add(y + y_offset)
                        required_height = calculate_row_height_dynamic(wrapped_value, font_size=11, col_width=50)
                        sheet.set_row(y + y_offset, required_height)
                    else:
                        sheet.write(y + y_offset, x_offset - 1, cell_value, col1_style)

            columns = lines[y]['columns']
            if options['show_growth_comparison'] and 'growth_comparison_data' in lines[y]:
                columns += [lines[y].get('growth_comparison_data')]
            filtered_columns_for_line = []
            column_expression_labels = []
            for i, column in enumerate(columns):
                if i < len(options['columns']):
                    original_column = options['columns'][i]
                    column_name = original_column.get('name', '').lower()
                    expression_label = original_column.get('expression_label', '').lower()

                    skip_column = False
                    for unwanted in unwanted_columns:
                        if unwanted in column_name or unwanted in expression_label:
                            skip_column = True
                            break
                    if not skip_column:
                        filtered_columns_for_line.append(column)
                        column_expression_labels.append(expression_label)
                else:
                    filtered_columns_for_line.append(column)
                    column_expression_labels.append('')

            wrapped_style = workbook.add_format({
                'font_name': 'Arial',
                'font_size': 11,
                'font_color': '#000000',
                'text_wrap': True,
                'valign': 'top',
                'border': 1,
                'border_color': '#CCCCCC'
            })
            
            long_text_style = workbook.add_format({
                'font_name': 'Arial',
                'font_size': 11,
                'font_color': '#000000',
                'text_wrap': True,
                'valign': 'top',
                'border': 1,
                'border_color': '#CCCCCC'
            })
            
            extra_long_text_style = workbook.add_format({
                'font_name': 'Arial',
                'font_size': 11,
                'font_color': '#000000',
                'text_wrap': True,
                'valign': 'top',
                'border': 1,
                'border_color': '#CCCCCC'
            })

            for x, column in enumerate(filtered_columns_for_line, start=x_offset + 1):
                cell_type, cell_value = self._get_cell_type_value(column)

                current_style = style
                
                # Check if this is a debit, credit, or balance column
                column_index = filtered_columns_for_line.index(column)
                if column_index < len(column_expression_labels):
                    expression_label = column_expression_labels[column_index]
                    if expression_label in ['debit', 'credit', 'balance']:
                        # Use currency style for these columns
                        if level == 0:
                            current_style = currency_bold_level0_style
                        elif level == 1:
                            current_style = currency_bold_level1_style
                        else:
                            current_style = currency_style
                
                if level >= 2 and isinstance(cell_value, str) and x == x_offset:
                    wrapped_text = wrap_text_dynamically(cell_value, max_line_length=120)
                    cell_value = wrapped_text
                    text_length = len(str(cell_value))
                    if text_length > 100:
                        current_style = extra_long_text_style
                    elif text_length > 50:
                        current_style = long_text_style
                    elif text_length > 20:
                        current_style = wrapped_style

                if cell_type == 'date':
                    from datetime import datetime
                    if isinstance(cell_value, str):
                        try:
                            date_obj = datetime.strptime(cell_value, '%d-%m-%y')
                            sheet.write_datetime(y + y_offset, x + lines[y].get('colspan', 1) - 1, date_obj,
                                                 date_default_style)
                        except:
                            sheet.write(y + y_offset, x + lines[y].get('colspan', 1) - 1, cell_value,
                                        date_default_style)
                    else:
                        sheet.write_datetime(y + y_offset, x + lines[y].get('colspan', 1) - 1, cell_value,
                                             date_default_style)
                else:
                    sheet.write(y + y_offset, x + lines[y].get('colspan', 1) - 1, cell_value, current_style)

            if level >= 2:
                description_text = ""
                if filtered_columns_for_line:
                    first_column = filtered_columns_for_line[0]
                    cell_type, cell_value = self._get_cell_type_value(first_column)
                    if isinstance(cell_value, str):
                        description_text = str(cell_value)
                
                if len(description_text) > 20:
                    wrapped_value = wrap_text_dynamically(cell_value, max_line_length=60)
                    # Merge A:B for first column
                    sheet.merge_range(y + y_offset, x_offset - 1, y + y_offset, x_offset, wrapped_value, col1_style)
                    merged_rows_ab.add(y + y_offset)
                    required_height = calculate_row_height_dynamic(wrapped_value, font_size=11, col_width=50)
                    sheet.set_row(y + y_offset, required_height)

        # Widen date columns to accommodate format like 31/Dec/2025
        sheet.set_column('A:A', 30)
        sheet.set_column('B:B', 30)
        sheet.set_column('C:C', 15)
        sheet.set_column('D:D', 15)
        sheet.set_column('E:E', 19)
        sheet.set_column('F:F', 19)
        sheet.set_column('G:G', 19)
        # After building all content, force-merge columns A and B for all used rows
        # to ensure a consistent A:B merged appearance even for empty cells.
        try:
            last_row = y_offset + len(lines) + 10
            for row in range(0, int(last_row)):
                if row in merged_rows_ab:
                    continue
                sheet.merge_range(row, 0, row, 1, '')
        except Exception as e:
            _logger.debug(f"A:B global merge ignored: {e}")

        # ================================
        # FOOTER
        # ================================
        footer_row = y_offset + len(lines) + 3

        footer = get_module_resource('grnlnd_task', 'static/src/img', 'partner_ledger.png')
        if footer:
            sheet.insert_image(f'A{footer_row}', footer, {'x_scale': 0.534, 'y_scale': 0.54})



    def export_partner_ledger_clean_xlsx(self, options):
        """Export Partner Ledger without error invoices to XLSX"""
        # Enable the hide error filter
        options['hide_error_invoices'] = True
        
        # Call the standard export method with modified options
        return self.export_to_xlsx(options)



class PartnerLedgerReportHandler(models.AbstractModel):
    _inherit = 'account.partner.ledger.report.handler'
    
    def _custom_options_initializer(self, report, options, previous_options=None):
        """Add custom filter for error invoices"""
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        
        # Add option to hide error invoices (default is False - show all)
        # Only hide when explicitly requested via context or previous options
        options['hide_error_invoices'] = False
        
        if previous_options and previous_options.get('hide_error_invoices'):
            options['hide_error_invoices'] = True
        
        if self.env.context.get('hide_error_invoices'):
            options['hide_error_invoices'] = True

        # Inject domain if filter is enabled
        if options.get('hide_error_invoices'):
            options.setdefault('forced_domain', [])
            options['forced_domain'] += [
                ('move_id.is_error_invoice', '!=', True),
                '!', '&',
                    ('move_id.reversal_move_id.is_error_invoice', '=', True),
                    ('move_id.reversal_move_id.state', '=', 'posted'),
            ]
        
        # Override buttons: PDF + XLSX dropdown, no Save button
        options['buttons'] = [
            {'name': _('PDF'), 'sequence': 10, 'action': 'export_file', 'action_param': 'export_to_pdf', 'file_export_type': _('PDF'), 'branch_allowed': True},
            {'name': _('XLSX'), 'sequence': 20, 'action': 'export_file', 'action_param': 'export_to_xlsx', 'file_export_type': _('XLSX'), 'branch_allowed': True},
            {'name': _('XLSX (No Reversals)'), 'sequence': 30, 'action': 'export_file', 'action_param': 'export_partner_ledger_clean_xlsx', 'file_export_type': _('XLSX'), 'branch_allowed': True},
        ]

    def _get_report_line_move_line(self, options, aml_query_result, partner_line_id, init_bal_by_col_group, level_shift=0):
        """Override to apply custom date formatting for invoice dates and due dates"""
        if aml_query_result['payment_id']:
            caret_type = 'account.payment'
        else:
            caret_type = 'account.move.line'

        columns = []
        report = self.env['account.report'].browse(options['report_id'])
        
        def format_date_to_dd_mmm_yyyy(date_str):
            if not date_str:
                return ''
            try:
                from datetime import datetime
                date_obj = datetime.strptime(str(date_str), '%Y-%m-%d')
                formatted_date = date_obj.strftime('%-d/%b/%Y')
                parts = formatted_date.split('/')
                if len(parts) == 3:
                    parts[1] = parts[1].capitalize()  
                    return '/'.join(parts)
                return formatted_date
            except:
                return date_str
        
        for column in options['columns']:
            col_expr_label = column['expression_label']
            col_value = aml_query_result[col_expr_label] if column['column_group_key'] == aml_query_result['column_group_key'] else None

            if col_value is None:
                columns.append(report._build_column_dict(None, None))
            else:
                currency = False

                if col_expr_label == 'balance':
                    col_value += init_bal_by_col_group[column['column_group_key']]

                if col_expr_label == 'amount_currency':
                    currency = self.env['res.currency'].browse(aml_query_result['currency_id'])
                    if currency == self.env.company.currency_id:
                        col_value = ''

                # Apply custom date formatting for invoice_date and date_maturity
                if col_expr_label in ['invoice_date', 'date_maturity'] and col_value:
                    col_value = format_date_to_dd_mmm_yyyy(col_value)

                columns.append(report._build_column_dict(col_value, column, options=options, currency=currency))

        return {
            'id': report._get_generic_line_id('account.move.line', aml_query_result['id'], parent_line_id=partner_line_id, markup=aml_query_result['partial_id']),
            'parent_id': partner_line_id,
            'name': self._format_aml_name(aml_query_result['name'], aml_query_result['ref'], aml_query_result['move_name']),
            'columns': columns,
            'caret_options': caret_type,
            'level': 3 + level_shift,
        }
