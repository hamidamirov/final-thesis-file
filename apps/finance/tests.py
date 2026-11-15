from datetime import date
from decimal import Decimal
from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Transaction


class MonthlyWorkbookTests(TestCase):
    def test_download_preserves_values_and_wraps_long_notes(self):
        users = get_user_model().objects
        user = users.create_user("report-student")
        other_user = users.create_user("other-student")
        today = timezone.localdate()
        note = "=" + "Long description of a monthly transaction. " * 5
        Transaction.objects.create(
            user=user, type=Transaction.Type.EXPENSE, category="Coffee",
            amount=Decimal("12.34"), date=today, note=note,
        )
        Transaction.objects.create(
            user=other_user, type=Transaction.Type.INCOME, category="Other user's transaction",
            amount=Decimal("25.00"), date=today,
        )
        previous_month = date(today.year - 1, today.month, 1)
        Transaction.objects.create(
            user=user, type=Transaction.Type.EXPENSE, category="Previous year",
            amount=Decimal("4.00"), date=previous_month,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("monthly_report_xlsx"), {"month": today.strftime("%Y-%m")})
        self.assertEqual(response.status_code, 200)
        self.assertIn(f"finance-report-{today:%Y-%m}.xlsx", response["Content-Disposition"])
        self.assertEqual(response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        with ZipFile(BytesIO(b"".join(response.streaming_content))) as download:
            sheet = ElementTree.fromstring(download.read("xl/worksheets/sheet1.xml"))
            styles = ElementTree.fromstring(download.read("xl/styles.xml"))
            strings = ElementTree.fromstring(download.read("xl/sharedStrings.xml"))

        values = [item.text for item in strings.findall("s:si/s:t", ns)]
        self.assertIn(note, values)
        self.assertNotIn("Other user's transaction", values)
        self.assertNotIn("Previous year", values)
        self.assertIsNone(sheet.find(".//s:f", ns))
        self.assertIsNone(sheet.find("s:autoFilter", ns))
        self.assertEqual(sheet.find(".//s:c[@r='D7']/s:v", ns).text, "12.34")
        note_style = int(sheet.find(".//s:c[@r='E7']", ns).attrib["s"])
        header_style = int(sheet.find(".//s:c[@r='E6']", ns).attrib["s"])
        formats = styles.find("s:cellXfs", ns)
        self.assertEqual(formats[note_style].find("s:alignment", ns).attrib["wrapText"], "1")
        self.assertNotEqual(formats[header_style].attrib["fillId"], formats[note_style].attrib["fillId"])
