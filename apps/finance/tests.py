from datetime import date
from decimal import Decimal
from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZipFile
from unittest.mock import patch
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.admin.models import LogEntry, CHANGE
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    AccountDeletionRequest, Budget, SavingsGoal, StudentOffer,
    StudentProfile, StudentVerificationRequest, Transaction,
)


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
        self.assertIn(f"finance-report-{today:%Y-%m}-01-to-{today:%Y-%m-%d}.xlsx", response["Content-Disposition"])
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


class ReportDateRangeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("range-student")
        self.client.force_login(self.user)
        for day, kind, amount in (
            (date(2026, 10, 14), "expense", "200"),
            (date(2026, 10, 15), "income", "100"),
            (date(2026, 11, 15), "expense", "30"),
            (date(2026, 11, 16), "income", "400"),
        ):
            Transaction.objects.create(user=self.user, date=day, type=kind, amount=amount, category=str(day))

    def test_cross_month_range_includes_both_boundaries_and_matches_exports(self):
        query = {"start_date": "2026-10-15", "end_date": "2026-11-15"}
        response = self.client.get(reverse("dashboard"), query)
        self.assertEqual(response.context["report_income"], Decimal("100"))
        self.assertEqual(response.context["report_expenses"], Decimal("30"))
        self.assertEqual(response.context["report_balance"], Decimal("70"))
        self.assertEqual(len(response.context["report_income_categories"]), 1)
        response = self.client.get(reverse("monthly_report_csv"), query)
        self.assertContains(response, "2026-10-15")
        self.assertContains(response, "2026-11-15")
        self.assertNotContains(response, "2026-10-14")
        self.assertNotContains(response, "2026-11-16")
        response = self.client.get(reverse("monthly_report_xlsx"), query)
        self.assertEqual(response.status_code, 200)
        with ZipFile(BytesIO(b"".join(response.streaming_content))) as download:
            sheet = ElementTree.fromstring(download.read("xl/worksheets/sheet1.xml"))
            strings = download.read("xl/sharedStrings.xml").decode()
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        self.assertEqual(sheet.find(".//s:c[@r='D4']/s:v", ns).text, "70")
        self.assertIn("2026-10-15", strings)
        self.assertIn("2026-11-15", strings)
        self.assertNotIn("2026-10-14", strings)
        self.assertNotIn("2026-11-16", strings)

    def test_transaction_history_range_works_with_search_and_type(self):
        response = self.client.get(reverse("dashboard"), {
            "transaction-start_date": "2026-10-15", "transaction-end_date": "2026-11-15",
            "type": "expense", "q": "2026-11",
        })
        entries = list(response.context["transactions"])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].date, date(2026, 11, 15))

    def test_invalid_ranges_are_rejected_in_page_and_exports(self):
        for query in (
            {"start_date": "2026-11-15", "end_date": "2026-10-15"},
            {"start_date": "invalid", "end_date": "2026-10-15"},
            {"start_date": "2026-10-15", "end_date": ""},
            {"start_date": "2026-10-15", "end_date": "9999-12-31"},
        ):
            with self.subTest(query=query):
                response = self.client.get(reverse("dashboard"), query)
                self.assertTrue(response.context["report_range"].errors)
                for route in ("monthly_report_xlsx", "monthly_report_csv"):
                    self.assertEqual(self.client.get(reverse(route), query).status_code, 400)

    def test_presets_and_legacy_month_links(self):
        from .date_ranges import DateRangeForm

        with patch("apps.finance.date_ranges.timezone.localdate", return_value=date(2026, 11, 19)):
            for preset, start in (("today", 19), ("week", 13), ("fortnight", 6), ("month", 1)):
                with self.subTest(preset=preset):
                    form = DateRangeForm({"period": preset}, default_month=True)
                    self.assertTrue(form.is_valid())
                    self.assertEqual(form.cleaned_data["start_date"], date(2026, 11, start))
                    self.assertEqual(form.cleaned_data["end_date"], date(2026, 11, 19))
            form = DateRangeForm({"month": "2026-10"}, month_key="month", default_month=True)
            self.assertEqual(form.cleaned_data["end_date"], date(2026, 10, 31))


class StudentStatusTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.user = users.create_user("student-status", email="personal@example.test")
        self.admin = users.create_superuser("student-reviewer", email="admin@example.test")
        self.profile = StudentProfile.objects.create(user=self.user)
        self.offer = StudentOffer.objects.create(
            title="Verified student offer", provider="Campus store",
            category="Food", discount_code="PRIVATE-STUDENT-CODE", is_active=True,
        )
        self.client.force_login(self.user)

    def submit_request(self):
        url = reverse("request_student_verification")
        response = self.client.post(url, {
            "action": "send", "university": "Example University",
            "university_email": "student@university.example",
        })
        self.assertRedirects(response, url)
        self.assertEqual(mail.outbox[-1].to, ["student@university.example"])
        self.assertContains(self.client.get(url), "university email")
        code = re.search(r"verification code is ([0-9]{6})\.", mail.outbox[-1].body)[1]
        self.assertEqual(self.client.post(url, {"action": "verify", "code": code}).status_code, 302)
        return StudentVerificationRequest.objects.filter(user=self.user).first()

    def test_verified_email_and_admin_approval_are_required_to_see_offers(self):
        dashboard = reverse("dashboard")
        self.assertNotContains(self.client.get(dashboard, {"offer_category": "Food"}), "PRIVATE-STUDENT-CODE")
        self.assertNotContains(self.client.get(dashboard), 'data-view="student-offers"')
        request = self.submit_request()
        self.assertEqual(request.status, "pending")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.account_type, StudentProfile.AccountType.OTHER)
        self.assertIsNotNone(request.email_verified_at)
        self.assertNotContains(self.client.get(dashboard), "PRIVATE-STUDENT-CODE")
        url = reverse("admin:finance_studentverificationrequest_review", args=[request.pk])
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 405)
        page = self.client.get(reverse("admin:finance_studentverificationrequest_change", args=[request.pk]))
        self.assertContains(page, 'value="approved"')
        self.assertEqual(self.client.post(url, {"decision": "approved", "review_note": "University domain checked."}).status_code, 302)
        request.refresh_from_db()
        self.assertEqual(request.reviewed_by, self.admin)
        self.assertEqual(request.status, "approved")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.account_type, StudentProfile.AccountType.STUDENT)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(dashboard), "PRIVATE-STUDENT-CODE")
        self.assertContains(self.client.get(dashboard), "University domain checked.")

    def test_declined_request_can_be_resubmitted_and_unprivileged_staff_cannot_approve(self):
        entry = self.submit_request()
        url = reverse("admin:finance_studentverificationrequest_review", args=[entry.pk])
        staff = get_user_model().objects.create_user("unauthorized-reviewer", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.post(url, {"decision": "approved"}).status_code, 403)
        self.client.force_login(self.admin)
        self.client.post(url, {"decision": "declined", "review_note": "Use your university address."})
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("dashboard")), "Use your university address.")
        self.assertNotContains(self.client.get(reverse("dashboard")), "PRIVATE-STUDENT-CODE")

        second = self.submit_request()
        self.assertNotEqual(second.pk, entry.pk)
        self.assertEqual(second.status, "pending")

    def test_code_required_and_profile_post_cannot_grant_access(self):
        self.client.post(reverse("request_student_verification"), {
            "action": "verify", "code": "123456",
        })
        self.assertFalse(StudentVerificationRequest.objects.exists())
        self.client.post(reverse("dashboard"), {
            "form_type": "profile", "email": self.user.email,
            "account_type": "student", "status": "approved",
        })
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.account_type, "other")
        self.assertNotContains(self.client.get(reverse("dashboard")), "PRIVATE-STUDENT-CODE")

    def test_registration_creates_a_regular_account_and_ignores_student_fields(self):
        self.client.logout()
        page = self.client.get(reverse("signup"))
        for name in ("account_type", "university", "university_email"):
            self.assertNotContains(page, f'name="{name}"')
        response = self.client.post(reverse("signup"), {
            "username": "new-university-student", "email": "new@example.test",
            "password1": "A-safe-signup-pass-42!", "password2": "A-safe-signup-pass-42!",
            "account_type": "student", "university": "Example University",
            "university_email": "new@university.example",
        })
        self.assertRedirects(response, reverse("signup_verify"))
        code = re.search(r"verification code is ([0-9]{6})\.", mail.outbox[-1].body)[1]
        self.client.post(reverse("signup_verify"), {"code": code})
        profile = StudentProfile.objects.get(user__username="new-university-student")
        self.assertEqual(profile.account_type, "other")
        self.assertEqual(profile.university_email, "")
        self.assertEqual(profile.university, "")
        self.assertFalse(StudentVerificationRequest.objects.filter(user=profile.user).exists())
        self.assertNotContains(self.client.get(reverse("dashboard")), "PRIVATE-STUDENT-CODE")

class AdministratorPrivacyTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.admin = users.create_user("daily-admin", is_staff=True)
        self.admin.groups.add(Group.objects.get(name="Platform administrators"))
        self.owner = users.create_user("private-student", email="private.student@example.test", password="Existing-password-42!")
        self.root = users.create_superuser("technical-admin", email="root@example.test")
        StudentProfile.objects.create(user=self.owner)
        self.client.force_login(self.admin)

    def test_admin_sections_match_sidebar_and_respect_role_permissions(self):
        for viewer in (self.admin, self.root):
            self.client.force_login(viewer)
            with self.subTest(viewer=viewer.username):
                page = self.client.get(reverse("admin:index"))
                for section in ("accounts", "requests", "content", "security"):
                    self.assertContains(page, f'overview-card--{section}')
                sidebar = self.client.get(reverse("admin:auth_user_changelist"))
                for section in ("accounts", "requests", "content", "security"):
                    self.assertContains(sidebar, f'admin-section-{section}')
                self.assertNotContains(page, 'class="overview-card overview-card--personal_finance"')
                self.assertNotContains(sidebar, "admin-section-personal_finance")
                self.assertNotContains(sidebar, 'href="/admin/finance/transaction/"')
                self.assertEqual(self.client.get("/admin/finance/userchallenge/").status_code, 404)

    def test_financial_admin_pages_are_removed_for_all_administrators(self):
        today = timezone.localdate()
        records = (
            Budget.objects.create(user=self.owner, category="Private budget", month=today.replace(day=1), amount=100),
            Transaction.objects.create(user=self.owner, type="expense", date=today, category="Private purchase", amount=10),
            SavingsGoal.objects.create(user=self.owner, name="Private goal", target_amount=100),
        )
        for viewer in (self.admin, self.root):
            self.client.force_login(viewer)
            for record in records:
                model = record._meta.model_name
                with self.subTest(viewer=viewer.username, model=model):
                    self.assertEqual(self.client.get(f"/admin/finance/{model}/").status_code, 404)
                    self.assertEqual(self.client.get(f"/admin/finance/{model}/{record.pk}/change/").status_code, 404)
                    self.assertEqual(self.client.post(f"/admin/finance/{model}/{record.pk}/change/", {}).status_code, 404)
        LogEntry.objects.create(
            user=self.root, content_type=ContentType.objects.get_for_model(Transaction),
            object_id=str(records[1].pk), object_repr="Private financial history", action_flag=CHANGE,
        )
        self.assertNotContains(self.client.get(reverse("admin:index")), "Private financial history")
        self.client.force_login(self.owner)
        page = self.client.get(reverse("dashboard"))
        for label in ("Private budget", "Private purchase", "Private goal"):
            self.assertContains(page, label)

    def test_masked_email_and_safe_account_updates(self):
        page = self.client.get(reverse("admin:auth_user_changelist"))
        self.assertContains(page, "p***@example.test")
        self.assertNotContains(page, self.owner.email)
        self.assertNotContains(page, self.root.username)
        url = reverse("admin:auth_user_change", args=[self.owner.pk])
        page = self.client.get(url)
        self.assertContains(page, "p***@example.test")
        self.assertNotContains(page, self.owner.email)
        self.assertNotContains(page, 'name="groups"')
        self.assertNotContains(page, 'name="is_superuser"')
        response = self.client.post(url, {
            "username": "renamed", "email": "hijack@example.test",
            "is_staff": "on", "is_superuser": "on", "password": "replacement",
        })
        self.assertEqual(response.status_code, 302)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.username, "private-student")
        self.assertEqual(self.owner.email, "private.student@example.test")
        self.assertFalse(self.owner.is_staff)
        self.assertFalse(self.owner.is_superuser)
        self.assertFalse(self.owner.is_active)
        self.assertTrue(self.owner.check_password("Existing-password-42!"))
        self.assertEqual(self.client.get(reverse("admin:auth_user_password_change", args=[self.owner.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:auth_user_delete", args=[self.owner.pk])).status_code, 403)
        self.admin.user_permissions.add(Permission.objects.get(content_type__app_label="core", codename="view_full_email"))
        self.assertNotContains(self.client.get(url), self.owner.email)
        self.assertNotContains(self.client.get(url, {"show_email": "1"}), self.owner.email)

    def test_superuser_cannot_reveal_emails_in_the_admin_panel(self):
        profile = self.owner.student_profile
        profile.university_email = "student@university.example"
        profile.save(update_fields=["university_email"])
        self.client.force_login(self.root)
        url = reverse("admin:auth_user_change", args=[self.owner.pk])
        page = self.client.get(url)
        self.assertContains(page, "p***@example.test")
        self.assertContains(page, "s***@university.example")
        self.assertNotContains(page, self.owner.email)
        self.assertNotContains(page, profile.university_email)
        self.assertNotContains(page, "Show full email")
        page = self.client.get(url, {"show_email": "1"})
        self.assertNotContains(page, self.owner.email)
        self.assertNotContains(page, profile.university_email)
        self.assertNotIn("email", page.context["adminform"].form.fields)
        self.client.force_login(self.admin)
        page = self.client.get(url, {"show_email": "1"})
        self.assertNotContains(page, self.owner.email)
        self.assertNotContains(page, "Show full email")

    def test_daily_admin_can_review_requests_but_cannot_delete_audit_history(self):
        request = StudentVerificationRequest.objects.create(
            user=self.owner, university="Example University",
            university_email="private.student@university.example", email_verified_at=timezone.now(),
        )
        url = reverse("admin:finance_studentverificationrequest_change", args=[request.pk])
        self.assertContains(self.client.get(url), "p***@university.example")
        self.assertNotContains(self.client.get(url), request.university_email)
        self.assertEqual(self.client.post(reverse("admin:finance_studentverificationrequest_review", args=[request.pk]), {
            "decision": "approved",
        }).status_code, 302)
        request.refresh_from_db()
        self.assertEqual(request.status, "approved")
        deletion = AccountDeletionRequest.objects.create(user=self.owner, username=self.owner.username, reason="Close my account")
        response = self.client.post(reverse("admin:finance_accountdeletionrequest_review", args=[deletion.pk]), {
            "decision": "decline",
        })
        self.assertEqual(response.status_code, 302)
        deletion.refresh_from_db()
        self.assertEqual(deletion.status, "declined")
        log = LogEntry.objects.create(
            user=self.admin, content_type=ContentType.objects.get_for_model(StudentVerificationRequest),
            object_id=str(request.pk), object_repr="Student review", action_flag=CHANGE,
        )
        self.assertEqual(self.client.post(reverse("manage_admin_activity"), {
            "action": "delete_entry", "entry_id": log.pk, "confirm": "yes",
        }).status_code, 403)
        self.assertTrue(LogEntry.objects.filter(pk=log.pk).exists())
        self.assertEqual(self.client.get(reverse("admin:auth_group_changelist")).status_code, 403)
        approved_deletion = AccountDeletionRequest.objects.create(
            user=self.owner, username=self.owner.username, reason="Confirmed closure",
        )
        self.assertEqual(self.client.post(
            reverse("admin:finance_accountdeletionrequest_review", args=[approved_deletion.pk]),
            {"decision": "accept", "confirm": "yes"},
        ).status_code, 302)
        self.assertFalse(get_user_model().objects.filter(pk=self.owner.pk).exists())
