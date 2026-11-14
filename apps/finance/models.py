from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.ui_text import ui_lazy


def first_day_of_current_month():
    return timezone.localdate().replace(day=1)


class PendingRegistration(models.Model):
    ATTEMPT_LIMIT = 4

    username = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    password_hash = models.CharField(max_length=128)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField(db_index=True)
    attempts_left = models.PositiveSmallIntegerField(default=ATTEMPT_LIMIT)
    blocked_until = models.DateTimeField(null=True, blank=True)
    resend_count = models.PositiveSmallIntegerField(default=0)


class AccountVerification(models.Model):
    class Purpose(models.TextChoices):
        LOGIN = "login", "Login"
        DELETION = "deletion", "Account deletion"
        EMAIL = "email", "Email change"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    purpose = models.CharField(max_length=8, choices=Purpose.choices)
    browser_hash = models.CharField(max_length=64)
    code_hash = models.CharField(max_length=128)
    account_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts_left = models.PositiveSmallIntegerField(default=5)
    blocked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "purpose"], name="unique_account_verification_purpose"),
        ]


class AccountDeletionRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", ui_lazy("Pending")
        ACCEPTED = "accepted", ui_lazy("Accepted")
        DECLINED = "declined", ui_lazy("Declined")
        CANCELLED = "cancelled", ui_lazy("Cancelled")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    username = models.CharField(max_length=150, verbose_name=ui_lazy("Username"))
    reason = models.CharField(max_length=1000, verbose_name=ui_lazy("Reason"))
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.PENDING, verbose_name=ui_lazy("Status"))
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name=ui_lazy("Requested at"))
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name=ui_lazy("Decided at"))
    hidden_from_profile = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviewed_account_deletion_requests", verbose_name=ui_lazy("Reviewed by"),
    )

    class Meta:
        ordering = ["-requested_at", "-pk"]
        verbose_name = ui_lazy("Account deletion request")
        verbose_name_plural = ui_lazy("Account deletion requests")

    def __str__(self):
        return self.username


class Budget(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_budgets",
    )
    category = models.CharField(max_length=100)
    month = models.DateField(default=first_day_of_current_month)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )

    class Meta:
        ordering = ["-month", "category"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "category", "month"],
                name="unique_user_category_month_budget",
            ),
        ]
        verbose_name = "budget"
        verbose_name_plural = "budgets"

    def __str__(self):
        return f"{self.category} budget ({self.month:%Y-%m})"


class SavingsGoal(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_savings_goals",
    )
    name = models.CharField(max_length=120)
    target_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    saved_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    target_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["target_date", "name"]
        verbose_name = "savings goal"
        verbose_name_plural = "savings goals"

    def __str__(self):
        return self.name


class FinancialTip(models.Model):
    title = models.CharField(max_length=160)
    category = models.CharField(max_length=80, blank=True)
    content = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "title"]
        verbose_name = "financial tip"
        verbose_name_plural = "financial tips"

    def __str__(self):
        return self.title


class SavingChallenge(models.Model):
    title = models.CharField(max_length=160)
    description = models.TextField()
    duration_days = models.PositiveSmallIntegerField(default=7)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["duration_days", "title"]
        verbose_name = "saving challenge"
        verbose_name_plural = "saving challenges"

    def __str__(self):
        return self.title


class UserChallenge(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_challenge_entries",
    )
    challenge = models.ForeignKey(
        SavingChallenge,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "challenge"],
                name="unique_user_saving_challenge",
            ),
        ]

    def __str__(self):
        return f"{self.user} — {self.challenge}"


class StudentOffer(models.Model):
    title = models.CharField(max_length=160)
    provider = models.CharField(max_length=120)
    category = models.CharField(max_length=80)
    description = models.TextField()
    discount_code = models.CharField(max_length=80, blank=True)
    offer_url = models.URLField(blank=True)
    valid_until = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "provider", "title"]
        verbose_name = "student offer"
        verbose_name_plural = "student offers"

    def __str__(self):
        return f"{self.provider}: {self.title}"


class Transaction(models.Model):
    class Type(models.TextChoices):
        INCOME = "income", ui_lazy("Income")
        EXPENSE = "expense", ui_lazy("Expense")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_transactions",
    )
    type = models.CharField(max_length=10, choices=Type.choices)
    category = models.CharField(max_length=100)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    date = models.DateField(default=timezone.localdate)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "transaction"
        verbose_name_plural = "transactions"

    def __str__(self):
        return f"{self.get_type_display()}: {self.category} ({self.amount})"


class StudentProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_profile",
    )
    university = models.CharField(max_length=180, blank=True)
    profile_picture = models.ImageField(upload_to="profile_pictures/", blank=True)

    def __str__(self):
        return f"{self.user.username}'s profile"
