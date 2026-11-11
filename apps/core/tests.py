from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from axes.models import AccessFailureLog, AccessLog


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

    def test_signup_still_logs_in_with_multiple_authentication_backends(self):
        username = "new-security-student"
        response = self.client.post(
            reverse("signup"),
            {
                "username": username,
                "email": "new-security-student@example.test",
                "password1": "Secure-signup-pass-542!",
                "password2": "Secure-signup-pass-542!",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(AccessLog.objects.filter(username=username).exists())
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
