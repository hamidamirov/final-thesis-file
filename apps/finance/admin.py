from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User

from .models import (
    Budget,
    FinancialTip,
    SavingChallenge,
    SavingsGoal,
    StudentOffer,
    StudentProfile,
    Transaction,
    UserChallenge,
)


class StudentProfileInline(admin.StackedInline):
    model = StudentProfile
    can_delete = False
    extra = 1
    max_num = 1
    fields = ("university", "profile_picture")


class StudentUserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "is_staff", "date_joined")
    list_filter = ("is_staff", "is_active", "date_joined")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("-date_joined",)
    inlines = (StudentProfileInline,)


admin.site.unregister(User)
admin.site.register(User, StudentUserAdmin)
admin.site.site_header = "Student Finance Administration"
admin.site.site_title = "Student Finance Admin"
admin.site.index_title = "Platform management"


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("month", "user", "category", "amount")
    list_filter = ("month", "category")
    search_fields = ("user__username", "category")
    autocomplete_fields = ("user",)
    date_hierarchy = "month"


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "user", "type", "category", "amount")
    list_filter = ("type", "date", "category")
    search_fields = ("user__username", "category", "note")
    date_hierarchy = "date"
    autocomplete_fields = ("user",)
    list_per_page = 25


@admin.register(SavingsGoal)
class SavingsGoalAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "saved_amount", "target_amount", "target_date")
    search_fields = ("name", "user__username")
    list_filter = ("target_date",)
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at",)


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
    autocomplete_fields = ("user", "challenge")


@admin.register(StudentOffer)
class StudentOfferAdmin(admin.ModelAdmin):
    list_display = ("title", "provider", "category", "is_active", "valid_until")
    list_filter = ("is_active", "category")
    search_fields = ("title", "provider", "category", "description", "discount_code")
    readonly_fields = ("created_at",)
    list_per_page = 25
