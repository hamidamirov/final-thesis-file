from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group, User

from apps.core.date_fields import PastOrTodayDatesAdmin
from apps.core.ui_text import localize_admin_model, localize_ui, ui_lazy

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


def permission_label(permission):
    content_type = permission.content_type
    model = content_type.model_class()
    action = permission.codename.removesuffix(f"_{content_type.model}")
    labels = {
        "add": "Can add {model}",
        "change": "Can change {model}",
        "delete": "Can delete {model}",
        "view": "Can view {model}",
    }
    if model is None or action not in labels:
        return str(permission)
    return f"{model._meta.app_config.verbose_name} | {content_type.name} | " + localize_ui(
        labels[action], model=model._meta.verbose_name
    )


class LocalizedPermissionsAdmin:
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        if field is not None and db_field.name in {"permissions", "user_permissions"}:
            field.queryset = field.queryset.select_related("content_type")
            field.label_from_instance = permission_label
        return field


class StudentGroupAdmin(LocalizedPermissionsAdmin, GroupAdmin):
    pass


class StudentUserAdmin(PastOrTodayDatesAdmin, LocalizedPermissionsAdmin, DjangoUserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "is_staff", "date_joined")
    list_filter = ("is_staff", "is_active", "date_joined")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("-date_joined",)
    inlines = (StudentProfileInline,)


admin.site.unregister(User)
admin.site.register(User, StudentUserAdmin)
admin.site.unregister(Group)
admin.site.register(Group, StudentGroupAdmin)
admin.site.site_header = ui_lazy("Student Finance Administration")
admin.site.site_title = ui_lazy("Student Finance Admin")
admin.site.index_title = ui_lazy("Platform management")

for model in (Budget, FinancialTip, SavingChallenge, SavingsGoal, StudentOffer, StudentProfile, Transaction, UserChallenge):
    localize_admin_model(model)


@admin.register(Budget)
class BudgetAdmin(PastOrTodayDatesAdmin, admin.ModelAdmin):
    list_display = ("month", "user", "category", "amount")
    list_filter = ("month", "category")
    search_fields = ("user__username", "category")
    autocomplete_fields = ("user",)
    date_hierarchy = "month"


@admin.register(Transaction)
class TransactionAdmin(PastOrTodayDatesAdmin, admin.ModelAdmin):
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
class UserChallengeAdmin(PastOrTodayDatesAdmin, admin.ModelAdmin):
    list_display = ("user", "challenge", "started_at", "completed_at")
    list_filter = ("challenge", "completed_at")
    search_fields = ("user__username", "challenge__title")
    autocomplete_fields = ("user", "challenge")


@admin.register(StudentOffer)
class StudentOfferAdmin(PastOrTodayDatesAdmin, admin.ModelAdmin):
    list_display = ("title", "provider", "category", "is_active", "valid_until")
    list_filter = ("is_active", "category")
    search_fields = ("title", "provider", "category", "description", "discount_code")
    readonly_fields = ("created_at",)
    list_per_page = 25
