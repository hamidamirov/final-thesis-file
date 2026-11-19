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
from apps.core.admin_permissions import SuperuserOnlyAdminMixin, mask_email
from apps.core.ui_text import localize_admin_model, localize_ui, ui_lazy

from .models import (
    AccountDeletionRequest,
    Budget,
    FinancialTip,
    SavingChallenge,
    SavingsGoal,
    StudentOffer,
    StudentProfile,
    StudentVerificationRequest,
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
            "can_review": request.user.has_perms(("finance.change_accountdeletionrequest", "finance.review_account_deletion")),
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
        if not request.user.has_perms(("finance.change_accountdeletionrequest", "finance.review_account_deletion")):
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
        if not request.user.has_perms(("finance.change_accountdeletionrequest", "finance.review_account_deletion")):
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
    fields = ("university", "profile_picture", "account_type", "masked_university_email")
    readonly_fields = ("account_type", "university_email", "masked_university_email")

    @admin.display(description=ui_lazy("University email"))
    def masked_university_email(self, obj):
        return mask_email(obj.university_email)


def permission_label(permission):
    if permission.codename in {"view_full_email", "delete_admin_history", "review_account_deletion"}:
        return localize_ui(permission.name)
    if permission.codename == "review_student_status" and permission.content_type.app_label == "finance":
        return localize_ui("Can review student status")
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


class StudentGroupAdmin(SuperuserOnlyAdminMixin, LocalizedPermissionsAdmin, GroupAdmin):
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
    list_display = ("username", "masked_email", "account_type", "is_active", "date_joined")
    list_filter = ("is_staff", "is_active", "date_joined")
    search_fields = ("username", "first_name", "last_name")
    ordering = ("-date_joined",)
    inlines = (StudentProfileInline,)

    def get_list_display(self, request):
        if request.user.is_superuser:
            return (*self.list_display, "is_staff", "is_superuser")
        return self.list_display

    def get_list_filter(self, request):
        return self.list_filter if request.user.is_superuser else ("is_active", "date_joined")

    @admin.display(description=ui_lazy("Email"))
    def masked_email(self, obj):
        return mask_email(obj.email)

    @admin.display(description=ui_lazy("Account type"))
    def account_type(self, obj):
        profile = getattr(obj, "student_profile", None)
        return profile.get_account_type_display() if profile else localize_ui("Other user")

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("student_profile")
        return queryset if request.user.is_superuser else queryset.filter(is_staff=False, is_superuser=False)

    def lookup_allowed(self, lookup, value, request=None):
        if "email" in lookup:
            return False
        return super().lookup_allowed(lookup, value, request)

    def get_fieldsets(self, request, obj=None):
        if request.user.is_superuser:
            fieldsets = super().get_fieldsets(request, obj)
            return tuple((title, {
                **options, "fields": tuple("masked_email" if field == "email" else field for field in options["fields"]),
            }) for title, options in fieldsets)
        return (
            (None, {"fields": ("username", "masked_email", "account_type", "is_active")}),
            (ui_lazy("Important dates"), {"fields": ("last_login", "date_joined")}),
        )

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            readonly = super().get_readonly_fields(request, obj)
            return (*readonly, "email", "masked_email")
        return ("username", "email", "masked_email", "account_type", "last_login", "date_joined")

    def get_inline_instances(self, request, obj=None):
        return super().get_inline_instances(request, obj) if request.user.is_superuser else []

    def has_add_permission(self, request):
        return request.user.is_superuser and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_delete_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if not request.user.is_superuser and obj and (obj.is_staff or obj.is_superuser):
            return False
        return super().has_change_permission(request, obj)

    def user_change_password(self, request, id, form_url=""):
        if not request.user.is_superuser:
            raise PermissionDenied
        return super().user_change_password(request, id, form_url)


admin.site.unregister(User)
admin.site.register(User, StudentUserAdmin)
admin.site.unregister(Group)
admin.site.register(Group, StudentGroupAdmin)
admin.site.site_header = ui_lazy("Student Finance Administration")
admin.site.site_title = ui_lazy("Student Finance Administration")
admin.site.index_title = ui_lazy("Platform management")

for model in (
    User, Group, AccountDeletionRequest, Budget, FinancialTip, SavingChallenge,
    SavingsGoal, StudentOffer, StudentProfile, StudentVerificationRequest, Transaction, UserChallenge,
):
    localize_admin_model(model)


@admin.register(StudentVerificationRequest)
class StudentVerificationRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "university", "masked_university_email", "status", "requested_at")
    list_filter = ("status",)
    search_fields = ("user__username", "university")
    readonly_fields = (
        "user", "university", "university_email", "email_verified_at",
        "requested_at", "status", "reviewed_at", "reviewed_by", "review_note", "masked_university_email",
    )
    fields = tuple(field for field in readonly_fields if field != "university_email")
    change_form_template = "admin/finance/studentverificationrequest/change_form.html"

    @admin.display(description=ui_lazy("University email"))
    def masked_university_email(self, obj):
        return mask_email(obj.university_email)

    def lookup_allowed(self, lookup, value, request=None):
        if "email" in lookup:
            return False
        return super().lookup_allowed(lookup, value, request)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if request.method == "POST":
            raise PermissionDenied
        extra_context = {
            **(extra_context or {}),
            "can_review": request.user.has_perms((
                "finance.change_studentverificationrequest", "finance.review_student_status",
            )),
        }
        return super().change_view(request, object_id, form_url, extra_context)

    def get_urls(self):
        return [
            path("<int:pk>/review/", self.admin_site.admin_view(self.review), name="finance_studentverificationrequest_review"),
            *super().get_urls(),
        ]

    @method_decorator(require_POST)
    @transaction.atomic
    def review(self, request, pk):
        if not request.user.has_perms((
            "finance.change_studentverificationrequest", "finance.review_student_status",
        )):
            raise PermissionDenied
        decision = request.POST.get("decision")
        if decision not in ("approved", "declined"):
            raise PermissionDenied
        entry = get_object_or_404(StudentVerificationRequest, pk=pk)
        get_object_or_404(User.objects.select_for_update(), pk=entry.user_id)
        entry = StudentVerificationRequest.objects.select_for_update().get(pk=pk)
        if entry.status != StudentVerificationRequest.Status.PENDING:
            self.message_user(request, localize_ui("This request has already been resolved."), messages.WARNING)
        else:
            entry.status = decision
            entry.reviewed_at = timezone.now()
            entry.reviewed_by = request.user
            entry.review_note = request.POST.get("review_note", "").strip()[:500]
            entry.save(update_fields=["status", "reviewed_at", "reviewed_by", "review_note"])
            profile, _ = StudentProfile.objects.get_or_create(user=entry.user)
            profile.account_type = (
                StudentProfile.AccountType.STUDENT if decision == "approved"
                else StudentProfile.AccountType.OTHER
            )
            profile.save(update_fields=["account_type"])
            self.log_change(request, entry, entry.get_status_display())
        return redirect(reverse("admin:finance_studentverificationrequest_change", args=[pk]))


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


@admin.register(StudentOffer)
class StudentOfferAdmin(admin.ModelAdmin):
    list_display = ("title", "provider", "category", "is_active", "valid_until")
    list_filter = ("is_active", "category")
    search_fields = ("title", "provider", "category", "description", "discount_code")
    readonly_fields = ("created_at",)
    list_per_page = 25
