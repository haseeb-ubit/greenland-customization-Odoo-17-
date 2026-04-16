# -*- coding: utf-8 -*-
import io
import base64
from odoo import models
from odoo.tools.pdf import PdfFileReader, PdfFileWriter


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        """
        Override to insert PDF attachments in sequence with other expense attachments.
        """
        content, content_type = super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)

        report = self._get_report(report_ref)
        if report.report_name != 'dp_portal_expense.report_petty_cash_with_invoices' or not res_ids:
            return content, content_type

        sheets = self.env['hr.expense.sheet'].browse(res_ids)
        
        # Build attachment info list
        attachment_info = []
        for sheet in sheets:
            for line in sheet.expense_line_ids:
                att = line.message_main_attachment_id
                if att and att.datas:
                    if att.mimetype == 'application/pdf':
                        try:
                            pdf_data = base64.b64decode(att.datas)
                            attachment_info.append(('pdf', pdf_data))
                        except Exception:
                            pass
                    elif att.mimetype.startswith('image/'):
                        attachment_info.append(('image', None))
        
        # If no PDF attachments, return original
        if not any(info[0] == 'pdf' for info in attachment_info):
            return content, content_type

        # Parse QWeb PDF and merge with PDF attachments
        qweb_reader = PdfFileReader(io.BytesIO(content), strict=False)
        writer = PdfFileWriter()
        
        # Page 0 is main table
        writer.addPage(qweb_reader.getPage(0))
        
        qweb_page_index = 1
        
        for att_type, pdf_data in attachment_info:
            if att_type == 'image':
                if qweb_page_index < qweb_reader.getNumPages():
                    writer.addPage(qweb_reader.getPage(qweb_page_index))
                    qweb_page_index += 1
            elif att_type == 'pdf':
                try:
                    pdf_reader = PdfFileReader(io.BytesIO(pdf_data), strict=False)
                    for i in range(pdf_reader.getNumPages()):
                        writer.addPage(pdf_reader.getPage(i))
                except Exception:
                    pass
        
        output = io.BytesIO()
        writer.write(output)
        return output.getvalue(), content_type
