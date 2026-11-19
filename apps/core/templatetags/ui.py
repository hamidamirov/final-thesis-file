from django import template
from django.contrib.admin.models import LogEntry
from django.db.models import Q

from apps.core.models import AdminActivityPreferences

from apps.core.ui_text import localize_ui, translate_ui, ui_lazy

register = template.Library()


@register.filter
def translate(value, language):
    return translate_ui(value, language)


@register.simple_tag(takes_context=True)
def tr(context, value, **values):
    language = context.get("site_language")
    return translate_ui(value, language, **values) if language else localize_ui(value, **values)


@register.simple_tag
def recent_admin_activity(user):
    preferences = AdminActivityPreferences.objects.filter(user=user).first()
    actions = LogEntry.objects.filter(user=user).exclude(
        content_type__app_label="finance",
        content_type__model__in=("transaction", "budget", "savingsgoal", "userchallenge"),
    ).select_related("content_type")
    can_restore = False
    if preferences:
        hidden = Q(pk__lte=preferences.cleared_through_id) | Q(
            pk__in=preferences.hidden_action_ids
        )
        can_restore = actions.filter(hidden).exists()
        actions = actions.exclude(hidden)
    return {
        "entries": actions[:10],
        "can_restore": can_restore,
    }


@register.filter
def admin_sections(app_list):
    definitions = (
        ("accounts", "Users and permissions", "Manage user accounts and administrator permissions.",
         ("auth.User", "auth.Group")),
        ("requests", "Requests", "Review student verification and account deletion requests.",
         ("finance.StudentVerificationRequest", "finance.AccountDeletionRequest")),
        ("content", "Student content", "Manage student offers, financial tips, and saving challenges.",
         ("finance.StudentOffer", "finance.FinancialTip", "finance.SavingChallenge")),
        ("security", "Security", "Review sign-in attempts and security records.",
         ("axes.AccessAttempt", "axes.AccessFailureLog", "axes.AccessLog")),
    )
    available = {
        f'{app["app_label"]}.{model["object_name"]}': {
            **model, "key": f'{app["app_label"]}-{model["object_name"].lower()}',
        }
        for app in app_list or () for model in app["models"]
    }
    sections = []
    for key, name, description, labels in definitions:
        models = [available.pop(label) for label in labels if label in available]
        if models:
            sections.append({
                "key": key, "name": ui_lazy(name), "description": ui_lazy(description), "models": models,
            })
    for app in app_list or ():
        models = []
        for model in app["models"]:
            label = f'{app["app_label"]}.{model["object_name"]}'
            if label in available:
                models.append(available[label])
        if models:
            sections.append({"key": app["app_label"], "name": app["name"], "models": models})
    return sections
