import re
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase
from django.db.models.query import QuerySet
from django.urls import reverse
from django.utils import timezone

from axes.models import AccessAttempt, AccessFailureLog, AccessLog

from apps.finance.models import AccountDeletionRequest, PendingRegistration, Transaction


class LoginSecurityTests(TestCase):
    def test_security_admin_pages_work_without_database_timezone_conversion(self):
        admin = get_user_model().objects.create_superuser(
            username="security-page-admin", email="admin@example.test",
            password="Secure-admin-pass-42!",
        )
        self.client.force_login(admin)
        AccessAttempt.objects.create(
            username="failed-user", ip_address="127.0.0.1",
            user_agent="test", attempt_time=timezone.now(), failures_since_start=1,
        )
        with patch.object(QuerySet, "datetimes", side_effect=ValueError("Missing database time zone definitions")):
            for model in (AccessAttempt, AccessFailureLog, AccessLog):
                with self.subTest(model=model._meta.model_name):
                    url = reverse(f"admin:axes_{model._meta.model_name}_changelist")
                    self.assertEqual(self.client.get(url).status_code, 200)
            response = self.client.get(reverse("admin:axes_accessattempt_changelist"), {
                "attempt_time__gte": timezone.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
            })
            self.assertContains(response, "failed-user")

    def test_failed_logins_are_logged_and_locked_after_limit(self):
        username = "security-check-user"
        get_user_model().objects.create_user(
            username=username,
            password="A-safe-test-password-42!",
        )

        for _ in range(settings.AXES_FAILURE_LIMIT):
            response = self.client.post(
                reverse("login"),
                {"username": username, "password": "incorrect-password"},
            )

        self.assertEqual(response.status_code, settings.AXES_HTTP_RESPONSE_CODE)
        self.assertEqual(
            AccessFailureLog.objects.filter(username=username).count(),
            settings.AXES_FAILURE_LIMIT,
        )

    def test_successful_login_is_recorded(self):
        username = "security-success-user"
        password = "A-safe-test-password-42!"
        get_user_model().objects.create_user(username=username, email="student@example.test", password=password)

        response = self.client.post(
            reverse("login"),
            {"username": "STUDENT@example.test", "password": password},
        )

        self.assertRedirects(response, reverse("login_verify"))
        self.assertContains(self.client.get(reverse("login_verify")), 'aria-label="Digit 6 of 6"')
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(AccessLog.objects.filter(username=username).exists())
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)
        code = re.search(r"verification code is ([0-9]{6})\.", mail.outbox[0].body)[1]
        incorrect = "000000" if code != "000000" else "000001"
        self.assertContains(self.client.post(reverse("login_verify"), {"code": incorrect}), "incorrect")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.post(reverse("login_verify"), {"code": code}).status_code, 302)
        self.assertTrue(AccessLog.objects.filter(username=username).exists())

    def test_admin_login_uses_the_same_failure_protection(self):
        username = "security-admin-check-user"
        get_user_model().objects.create_superuser(
            username=username,
            email="security-admin-check@example.test",
            password="A-safe-test-password-42!",
        )

        for _ in range(settings.AXES_FAILURE_LIMIT):
            response = self.client.post(
                reverse("admin:login"),
                {"username": username, "password": "incorrect-password"},
            )

        self.assertEqual(response.status_code, settings.AXES_HTTP_RESPONSE_CODE)
        self.assertEqual(
            AccessFailureLog.objects.filter(username=username).count(),
            settings.AXES_FAILURE_LIMIT,
        )


class RegistrationVerificationTests(TestCase):
    username = "new-security-student"
    email = "new-security-student@example.test"

    def test_signup_rejects_passwords_missing_required_characters(self):
        for password in ("lowercase-42!", "Uppercase-without-number!", "UppercaseNoSymbol42"):
            with self.subTest(password=password):
                response = self.client.post(reverse("signup"), {
                    "username": self.username,
                    "email": self.email,
                    "password1": password,
                    "password2": password,
                })
                self.assertTrue(response.context["form"].errors["password2"])
        self.assertFalse(PendingRegistration.objects.exists())
        self.assertFalse(mail.outbox)

    def start_registration(self, client=None):
        return (client or self.client).post(
            reverse("signup"),
            {
                "username": self.username,
                "email": self.email,
                "password1": "Secure-signup-pass-542!",
                "password2": "Secure-signup-pass-542!",
            },
        )

    def test_signup_sends_code_and_logs_in_only_after_verification(self):
        self.assertRedirects(self.start_registration(), reverse("signup_verify"))
        self.assertFalse(get_user_model().objects.filter(username=self.username).exists())

        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.email])
        code = re.search(r"verification code is ([0-9]{6})\.", mail.outbox[0].body)[1]

        response = self.client.post(reverse("signup_verify"), {"code": code})

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        user = get_user_model().objects.get(username=self.username)
        self.assertTrue(user.check_password("Secure-signup-pass-542!"))
        self.assertFalse(PendingRegistration.objects.filter(email=self.email).exists())
        self.assertTrue(AccessLog.objects.filter(username=self.username).exists())
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_fourth_incorrect_attempt_blocks_new_codes_for_fifteen_minutes(self):
        self.start_registration()
        code = re.search(r"verification code is ([0-9]{6})\.", mail.outbox[0].body)[1]
        incorrect = "000000" if code != "000000" else "000001"

        for _ in range(3):
            self.client.post(reverse("signup_verify"), {"code": incorrect})
        self.assertIsNone(PendingRegistration.objects.get(email=self.email).blocked_until)
        before = timezone.now()
        self.client.post(reverse("signup_verify"), {"code": incorrect})
        response = self.client.post(reverse("signup_verify"), {"code": code})

        self.assertContains(response, "Too many incorrect codes")
        self.assertFalse(get_user_model().objects.filter(username=self.username).exists())
        pending = PendingRegistration.objects.get(email=self.email)
        self.assertGreaterEqual(pending.blocked_until, before + timedelta(minutes=15))
        self.assertLessEqual(pending.blocked_until, timezone.now() + timedelta(minutes=15))

        other_browser = Client()
        pending.expires_at = before - timedelta(seconds=1)
        pending.save(update_fields=["expires_at"])
        self.assertContains(self.start_registration(other_browser), "15-minute lockout")
        blocked_resend = self.client.post(reverse("signup_verify"), {"action": "resend"})
        self.assertContains(blocked_resend, "Wait until the lockout ends")
        self.assertEqual(len(mail.outbox), 1)

        pending.blocked_until = timezone.now() - timedelta(seconds=1)
        pending.save(update_fields=["blocked_until"])
        resend = self.client.post(reverse("signup_verify"), {"action": "resend"})
        self.assertRedirects(resend, reverse("signup_verify"))
        self.assertEqual(len(mail.outbox), 2)
        new_code = re.search(r"verification code is ([0-9]{6})\.", mail.outbox[1].body)[1]
        verified = self.client.post(reverse("signup_verify"), {"code": new_code})
        self.assertRedirects(verified, reverse("home"), fetch_redirect_response=False)

    def test_can_request_at_most_three_new_codes_after_expiry(self):
        self.start_registration()
        verify_url = reverse("signup_verify")
        response = self.client.post(verify_url, {"action": "resend"})
        self.assertContains(response, "Wait for the current code to expire")
        self.assertEqual(len(mail.outbox), 1)

        for _ in range(3):
            PendingRegistration.objects.filter(email=self.email).update(
                expires_at=timezone.now() - timedelta(seconds=1)
            )
            self.assertRedirects(self.client.post(verify_url, {"action": "resend"}), verify_url)
        self.assertEqual(len(mail.outbox), 4)

        PendingRegistration.objects.filter(email=self.email).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        response = self.client.post(verify_url, {"action": "resend"})
        self.assertContains(response, "limit of three new codes")
        self.assertRedirects(self.start_registration(), verify_url)
        self.assertContains(self.start_registration(Client()), "registration is already in progress")
        self.assertEqual(len(mail.outbox), 4)

    def test_expired_code_cannot_be_used(self):
        before = timezone.now()
        self.start_registration()
        expires_at = PendingRegistration.objects.get(email=self.email).expires_at
        self.assertGreaterEqual(expires_at, before + timedelta(minutes=2))
        self.assertLessEqual(expires_at, timezone.now() + timedelta(minutes=2))
        code = re.search(r"verification code is ([0-9]{6})\.", mail.outbox[0].body)[1]
        with patch("apps.finance.views.timezone.now", return_value=expires_at - timedelta(seconds=30)):
            response = self.client.get(reverse("signup_verify"))
            self.assertEqual(response.context["remaining_ms"], 30000)
            self.assertContains(response, 'data-remaining-ms="30000"')

        with patch("apps.finance.views.timezone.now", return_value=expires_at):
            response = self.client.post(reverse("signup_verify"), {"code": code})

        self.assertContains(response, "This code is no longer valid")
        self.assertFalse(get_user_model().objects.filter(username=self.username).exists())

class AccountDeletionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.student = users.create_user("student-to-review", email="student@example.test")
        cls.staff = users.create_user("staff", is_staff=True)
        cls.admin = users.create_superuser("reviewer", email="admin@example.test")

    def test_email_change_requires_a_code_from_the_existing_address(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse("dashboard"), {
            "form_type": "profile", "email": "new@example.test",
        })
        self.assertRedirects(response, reverse("verify_email_change"))
        self.student.refresh_from_db()
        self.assertEqual(self.student.email, "student@example.test")
        self.assertEqual(mail.outbox[-1].to, ["student@example.test"])
        code = re.search(r"verification code is ([0-9]{6})\.", mail.outbox[-1].body)[1]
        self.client.post(reverse("verify_email_change"), {"code": code})
        self.student.refresh_from_db()
        self.assertEqual(self.student.email, "new@example.test")

    def test_user_verification_and_admin_review(self):
        self.client.force_login(self.student)
        request_url = reverse("request_account_deletion")
        self.assertRedirects(self.client.post(request_url, {
            "action": "send", "reason": "I no longer use this account.",
        }), request_url)
        self.assertFalse(AccountDeletionRequest.objects.exists())
        self.assertContains(self.client.get(request_url), 'aria-label="Digit 6 of 6"')
        self.assertContains(self.client.get(request_url), 'id="verification-countdown"')
        code = re.search(r"verification code is ([0-9]{6})\.", mail.outbox[-1].body)[1]
        self.client.post(request_url, {"action": "verify", "code": code})
        entry = AccountDeletionRequest.objects.get(user=self.student)
        self.assertEqual(entry.status, AccountDeletionRequest.Status.PENDING)
        self.assertEqual(entry.reason, "I no longer use this account.")
        self.assertIsNotNone(entry.requested_at)

        review_url = reverse("admin:finance_accountdeletionrequest_review", args=[entry.pk])
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(review_url, {"decision": "accept"}).status_code, 403)

        self.client.force_login(self.admin)
        change_url = reverse("admin:finance_accountdeletionrequest_change", args=[entry.pk])
        review_page = self.client.get(change_url)
        self.assertContains(review_page, f'formaction="{review_url}"')
        self.assertContains(review_page, entry.reason)
        self.assertEqual(self.client.get(review_url).status_code, 405)
        self.assertEqual(self.client.post(review_url, {"decision": "decline"}).status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.status, AccountDeletionRequest.Status.DECLINED)
        self.assertTrue(get_user_model().objects.filter(pk=self.student.pk).exists())

        self.client.force_login(self.student)
        status_url = reverse("account_deletion_status")
        self.assertContains(self.client.get(status_url), "The administrator declined")
        self.assertContains(self.client.get(status_url), "Create a new request")
        self.client.post(request_url, {"action": "remove", "request_id": entry.pk})
        self.assertNotContains(self.client.get(status_url), "The administrator declined")
        entry.refresh_from_db()
        self.assertTrue(entry.hidden_from_profile)
        self.assertEqual(entry.status, AccountDeletionRequest.Status.DECLINED)
        self.assertContains(self.client.get(request_url), "Send verification code")

        self.client.force_login(self.admin)
        entry = AccountDeletionRequest.objects.create(
            user=self.student, username=self.student.username, reason="Please close my account.",
        )
        review_url = reverse("admin:finance_accountdeletionrequest_review", args=[entry.pk])
        confirm_url = reverse("admin:finance_accountdeletionrequest_confirm", args=[entry.pk])
        self.assertRedirects(self.client.post(review_url, {"decision": "accept"}), confirm_url)
        confirm_page = self.client.get(confirm_url)
        self.assertContains(confirm_page, "admin-delete-panel")
        self.assertContains(confirm_page, self.student.username)
        self.assertTrue(get_user_model().objects.filter(pk=self.student.pk).exists())
        self.assertEqual(self.client.post(review_url, {"decision": "accept", "confirm": "yes"}).status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.status, AccountDeletionRequest.Status.ACCEPTED)
        self.assertEqual(entry.reviewed_by, self.admin)
        self.assertIsNone(entry.user)
        self.assertFalse(get_user_model().objects.filter(pk=self.student.pk).exists())


class TransactionCategoryTests(TestCase):
    def test_select_and_save_a_custom_category_for_reuse(self):
        user = get_user_model().objects.create_user("category-student")
        self.client.force_login(user)
        dashboard = reverse("dashboard")
        self.assertContains(self.client.get(dashboard), '<option value="Coffee">Coffee</option>', html=True)
        data = {"form_type": "transaction", "type": "expense", "amount": "4", "date": timezone.localdate().isoformat()}
        response = self.client.post(dashboard, {**data, "category_choice": "Salary"})
        self.assertContains(response, "Choose a category for this transaction type.")
        self.assertFalse(Transaction.objects.filter(user=user).exists())
        self.client.post(dashboard, {**data, "category_choice": "Coffee"})
        self.assertTrue(Transaction.objects.filter(user=user, category="Coffee").exists())
        self.client.post(dashboard, {**data, "category_choice": "__custom_category__", "category": "Bike repair"})
        entry = Transaction.objects.get(user=user, category="Bike repair")
        self.assertContains(self.client.get(dashboard), '<option value="Bike repair">Bike repair</option>', html=True)
        self.assertContains(
            self.client.get(reverse("transaction_edit", args=[entry.pk])),
            '<option value="Bike repair" selected>Bike repair</option>', html=True,
        )

    def test_existing_food_category_is_localized_in_the_picker(self):
        user = get_user_model().objects.create_user("legacy-category-student")
        entry = Transaction.objects.create(
            user=user, type="expense", category="yemey", amount=4, date=timezone.localdate(),
        )
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse("dashboard")), '<option value="yemey">Food</option>', html=True)
        session = self.client.session
        session["site_language"] = "az"
        session.save()
        self.assertContains(
            self.client.get(reverse("transaction_edit", args=[entry.pk])),
            '<option value="yemey" selected>Qida</option>', html=True,
        )
