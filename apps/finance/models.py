from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


def first_day_of_current_month():
    return timezone.localdate().replace(day=1)


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


class Transaction(models.Model):
    class Type(models.TextChoices):
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

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
