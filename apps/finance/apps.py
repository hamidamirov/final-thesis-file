from django.apps import AppConfig

from apps.core.ui_text import ui_lazy


class FinanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.finance"
    verbose_name = ui_lazy("Finance")
