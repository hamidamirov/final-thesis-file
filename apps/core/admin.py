from axes.admin import AccessFailureLogAdmin, AccessLogAdmin
from axes.models import AccessAttempt, AccessFailureLog, AccessLog
from django.apps import apps
from django.contrib import admin

from .models import AdminActivityPreferences
from .ui_text import localize_admin_model, ui_lazy


apps.get_app_config("axes").verbose_name = ui_lazy("Security")
for model in (AccessAttempt, AccessFailureLog, AccessLog, AdminActivityPreferences):
    localize_admin_model(model)

class StudentBudgetAccessLogAdmin(AccessLogAdmin):
    # The sidebar date filters work without MySQL named time zone tables.
    date_hierarchy = None


class StudentBudgetAccessFailureLogAdmin(AccessFailureLogAdmin):
    date_hierarchy = None


for model, admin_class in (
    (AccessLog, StudentBudgetAccessLogAdmin),
    (AccessFailureLog, StudentBudgetAccessFailureLogAdmin),
):
    if admin.site.is_registered(model):
        admin.site.unregister(model)
        admin.site.register(model, admin_class)
