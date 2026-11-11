import re
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from axes.models import AccessFailureLog, AccessLog

from apps.finance.models import PendingRegistration


class LoginSecurityTests(TestCase):
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
        get_user_model().objects.create_user(username=username, password=password)

        response = self.client.post(
            reverse("login"),
            {"username": username, "password": password},
        )

        self.assertEqual(response.status_code, 302)
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
