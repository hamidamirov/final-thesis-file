from django.contrib import admin

from .models import (
    Budget,
    FinancialTip,
    SavingChallenge,
    SavingsGoal,
    Transaction,
    UserChallenge,
)


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("month", "user", "category", "amount")
    list_filter = ("month", "category")
    search_fields = ("user__username", "category")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "user", "type", "category", "amount")
    list_filter = ("type", "date", "category")
    search_fields = ("user__username", "category", "note")
    date_hierarchy = "date"


@admin.register(SavingsGoal)
class SavingsGoalAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "saved_amount", "target_amount", "target_date")
    search_fields = ("name", "user__username")


@admin.register(FinancialTip)
class FinancialTipAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "is_active", "created_at")
    list_filter = ("is_active", "category")
    search_fields = ("title", "content", "category")


@admin.register(SavingChallenge)
class SavingChallengeAdmin(admin.ModelAdmin):
    list_display = ("title", "duration_days", "is_active", "created_at")
    list_filter = ("is_active", "duration_days")
    search_fields = ("title", "description")


@admin.register(UserChallenge)
class UserChallengeAdmin(admin.ModelAdmin):
    list_display = ("user", "challenge", "started_at", "completed_at")
    list_filter = ("challenge", "completed_at")
    search_fields = ("user__username", "challenge__title")
