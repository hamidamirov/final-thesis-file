from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import GroupAdmin, UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET, require_POST

from apps.core.date_fields import PastOrTodayDatesAdmin
from apps.core.ui_text import localize_admin_model, localize_ui, ui_lazy

from .models import (
    AccountDeletionRequest,
    Budget,
    FinancialTip,
    SavingChallenge,
    SavingsGoal,
    StudentOffer,
    StudentProfile,
    Transaction,
    UserChallenge,
)


@admin.register(AccountDeletionRequest)
class AccountDeletionRequestAdmin(admin.ModelAdmin):
    list_display = ("username", "reason", "requested_at", "status")
    list_filter = ("status",)
    search_fields = ("username", "reason")
    readonly_fields = ("user", "username", "reason", "requested_at", "status", "decided_at", "reviewed_by")
    fields = readonly_fields
    change_form_template = "admin/finance/accountdeletionrequest/change_form.html"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if request.method == "POST":
            raise PermissionDenied
        extra_context = {
            **(extra_context or {}),
            "can_review": request.user.has_perms(("finance.change_accountdeletionrequest", "auth.delete_user")),
        }
        return super().change_view(request, object_id, form_url, extra_context)

    def get_urls(self):
        return [
            path("<int:pk>/confirm/", self.admin_site.admin_view(self.confirm_accept), name="finance_accountdeletionrequest_confirm"),
            path("<int:pk>/review/", self.admin_site.admin_view(self.review), name="finance_accountdeletionrequest_review"),
            *super().get_urls(),
        ]

    @method_decorator(require_GET)
    def confirm_accept(self, request, pk):
        if not request.user.has_perms(("finance.change_accountdeletionrequest", "auth.delete_user")):
            raise PermissionDenied
        entry = get_object_or_404(AccountDeletionRequest.objects.select_related("user"), pk=pk)
        change_url = reverse("admin:finance_accountdeletionrequest_change", args=[pk])
        if entry.status != AccountDeletionRequest.Status.PENDING:
            self.message_user(request, localize_ui("This request has already been resolved."), messages.WARNING)
            return redirect(change_url)
        if not entry.user or entry.user.is_staff or entry.user.is_superuser:
            self.message_user(request, localize_ui("This account cannot be deleted through this request."), messages.ERROR)
            return redirect(change_url)
        return render(request, "admin/finance/accountdeletionrequest/confirm_accept.html", {
            **self.admin_site.each_context(request),
            "title": localize_ui("Confirm account deletion"),
            "entry": entry,
            "change_url": change_url,
        })

    @method_decorator(require_POST)
    @transaction.atomic
    def review(self, request, pk):
        decision = request.POST.get("decision")
        if not request.user.has_perms(("finance.change_accountdeletionrequest", "auth.delete_user")):
            raise PermissionDenied
        if decision not in ("accept", "decline"):
            raise PermissionDenied
        if decision == "accept" and request.POST.get("confirm") != "yes":
            return redirect("admin:finance_accountdeletionrequest_confirm", pk=pk)

        entry = get_object_or_404(AccountDeletionRequest, pk=pk)
        user = User.objects.select_for_update().filter(pk=entry.user_id).first()
        entry = AccountDeletionRequest.objects.select_for_update().get(pk=pk)
        if entry.status != AccountDeletionRequest.Status.PENDING:
            self.message_user(request, localize_ui("This request has already been resolved."), messages.WARNING)
        elif decision == "accept" and (not user or user.is_staff or user.is_superuser):
            self.message_user(request, localize_ui("This account cannot be deleted through this request."), messages.ERROR)
        else:
            entry.status = AccountDeletionRequest.Status.ACCEPTED if decision == "accept" else AccountDeletionRequest.Status.DECLINED
            entry.decided_at = timezone.now()
            entry.reviewed_by = request.user
            entry.save(update_fields=["status", "decided_at", "reviewed_by"])
            if decision == "accept":
                profile = getattr(user, "student_profile", None)
                if profile and profile.profile_picture:
                    picture = profile.profile_picture
                    transaction.on_commit(lambda: picture.storage.delete(picture.name), robust=True)
                user.delete()
            self.log_change(request, entry, entry.get_status_display())
        return redirect(reverse("admin:finance_accountdeletionrequest_change", args=[pk]))


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


class StudentAdminPasswordChangeForm(AdminPasswordChangeForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        if "usable_password" in self.fields:
            field = self.fields["usable_password"]
            field.label = ui_lazy("Password-based authentication")
            field.choices = [("true", ui_lazy("Enabled")), ("false", ui_lazy("Disabled"))]
            field.help_text = ui_lazy("Controls whether this user can sign in with a password.")


class StudentUserAdmin(PastOrTodayDatesAdmin, LocalizedPermissionsAdmin, DjangoUserAdmin):
    change_password_form = StudentAdminPasswordChangeForm
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
