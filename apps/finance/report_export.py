from io import BytesIO

from xlsxwriter import Workbook

from apps.core.ui_text import translate_ui

from .models import Transaction


def monthly_workbook(month, transactions, income, expenses, language):
    output = BytesIO()
    with Workbook(output, {"in_memory": True}) as workbook:
        sheet = workbook.add_worksheet(translate_ui("Monthly report", language))
        sheet.hide_gridlines(2)
        for column, width in enumerate((16, 17, 30, 17, 62)):
            sheet.set_column(column, column, width)

        title = workbook.add_format({
            "font_color": "#173B67", "font_size": 16, "bold": True,
            "valign": "vcenter", "indent": 1,
        })
        header = workbook.add_format({
            "bg_color": "#ECF3FA", "font_color": "#173B67", "bold": True,
            "text_wrap": True, "valign": "vcenter", "indent": 1,
        })
        money_format = "#,##0.00;[Red]-#,##0.00"
        sheet.merge_range(0, 0, 0, 4, f'{translate_ui("Monthly report", language)}  ·  {month:%Y-%m}', title)
        sheet.set_row(0, 36)

        for row, (label, value, fill) in enumerate((
            ("Total income", income, "#F6F8FB"),
            ("Total expenses", expenses, "#F6F8FB"),
            ("Monthly balance", income - expenses, "#E8F1FB"),
        ), start=1):
            summary_style = {
                "bg_color": fill, "font_color": "#173B67", "bold": row == 3,
                "valign": "vcenter", "indent": 1,
            }
            summary = workbook.add_format(summary_style)
            summary_amount = workbook.add_format({
                **summary_style, "num_format": money_format, "align": "right",
            })
            sheet.merge_range(row, 0, row, 2, translate_ui(label, language), summary)
            sheet.write_number(row, 3, value, summary_amount)
            sheet.set_row(row, 22)

        header_row = 5
        sheet.write_row(header_row, 0, [
            translate_ui(label, language) for label in ("Date", "Type", "Category", "Amount", "Note")
        ], header)
        sheet.set_row(header_row, 23)
        sheet.freeze_panes(header_row + 1, 0)

        row_styles = []
        for fill in ("#FFFFFF", "#F7F9FC"):
            base = {"bg_color": fill, "font_color": "#172B45", "valign": "top"}
            row_styles.append((
                workbook.add_format({**base, "num_format": "yyyy-mm-dd", "align": "left", "indent": 1}),
                workbook.add_format({**base, "text_wrap": True, "indent": 1}),
                workbook.add_format({**base, "num_format": money_format, "align": "right", "indent": 1}),
            ))

        for row, entry in enumerate(transactions, start=header_row + 1):
            date_style, text_style, amount_style = row_styles[(row - header_row - 1) % 2]
            is_income = entry.type == Transaction.Type.INCOME
            sheet.write_datetime(row, 0, entry.date, date_style)
            sheet.write_string(
                row, 1, translate_ui("Income" if is_income else "Expense", language),
                text_style,
            )
            sheet.write_string(row, 2, entry.category, text_style)
            sheet.write_number(row, 3, entry.amount, amount_style)
            sheet.write_string(row, 4, entry.note, text_style)

    output.seek(0)
    return output
