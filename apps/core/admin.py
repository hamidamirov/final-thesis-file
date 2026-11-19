from axes.admin import AccessAttemptAdmin, AccessFailureLogAdmin, AccessLogAdmin, IsLockedOutFilter
from axes.conf import settings as axes_settings
from axes.models import AccessAttempt, AccessFailureLog, AccessLog
from django.apps import apps
from django.contrib import admin

from .models import AdminActivityPreferences
from .ui_text import localize_admin_model, localize_ui, ui_lazy


apps.get_app_config("axes").verbose_name = ui_lazy("Security")
for model in (AccessAttempt, AccessFailureLog, AccessLog, AdminActivityPreferences):
    localize_admin_model(model)

class LocalizedLockedOutFilter(IsLockedOutFilter):
    title = ui_lazy("Locked out")

    def lookups(self, request, model_admin):
        return (("yes", ui_lazy("Yes")), ("no", ui_lazy("No")))


class SecurityLogPrivacyMixin:
    def lookup_allowed(self, lookup, value, request=None):
        if request and not request.user.is_superuser and lookup.split("__")[0] in {"get_data", "post_data", "http_accept"}:
            return False
        return super().lookup_allowed(lookup, value, request)

    def get_fieldsets(self, request, obj=None):
        if request.user.is_superuser:
            return tuple(
                (localize_ui(title) if title else title, options)
                for title, options in super().get_fieldsets(request, obj)
            )
        fields = tuple(name for name in self.list_display if name not in {"status", "expiration"})
        return ((None, {"fields": fields}),)

    def get_readonly_fields(self, request, obj=None):
        return tuple(dict.fromkeys((*super().get_readonly_fields(request, obj), *self.list_display)))


class StudentBudgetAccessAttemptAdmin(SecurityLogPrivacyMixin, AccessAttemptAdmin):
    # Use the sidebar date filters without requiring MySQL time zone tables.
    date_hierarchy = None

    def get_list_filter(self, request):
        return tuple(
            LocalizedLockedOutFilter if item is IsLockedOutFilter else item
            for item in super().get_list_filter(request)
        )

    @admin.display(description=ui_lazy("Status"))
    def status(self, obj):
        remaining = axes_settings.AXES_FAILURE_LIMIT - obj.failures_since_start
        return localize_ui("Attempts remaining: {count}", count=remaining) if remaining > 0 else localize_ui("Locked out")

    @admin.display(description=ui_lazy("Expires at"))
    def expiration(self, obj):
        return obj.expiration.expires_at if hasattr(obj, "expiration") else localize_ui("Not set")

    @admin.action(description=ui_lazy("Clean up expired attempts"))
    def cleanup_expired_attempts(self, request, queryset):
        count = self.handler.clean_expired_user_attempts(request=request)
        self.message_user(request, localize_ui("Cleaned up {count} expired access attempts.", count=count))


class StudentBudgetAccessLogAdmin(SecurityLogPrivacyMixin, AccessLogAdmin):
    # The sidebar date filters work without MySQL named time zone tables.
    date_hierarchy = None


class StudentBudgetAccessFailureLogAdmin(SecurityLogPrivacyMixin, AccessFailureLogAdmin):
    date_hierarchy = None


for model, admin_class in (
    (AccessAttempt, StudentBudgetAccessAttemptAdmin),
    (AccessLog, StudentBudgetAccessLogAdmin),
    (AccessFailureLog, StudentBudgetAccessFailureLogAdmin),
):
    if admin.site.is_registered(model):
        admin.site.unregister(model)
        admin.site.register(model, admin_class)
