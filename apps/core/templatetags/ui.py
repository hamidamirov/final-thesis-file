from django import template
from django.contrib.admin.models import LogEntry
from django.db.models import Q

from apps.core.models import AdminActivityPreferences

from apps.core.ui_text import localize_ui, translate_ui

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
    actions = LogEntry.objects.filter(user=user).select_related("content_type")
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
def admin_overview_order(app_list):
    priorities = {"auth": 0, "axes": 1, "finance": 2}
    apps = sorted(
        app_list or (),
        key=lambda app: (priorities.get(app["app_label"], len(priorities)), app["app_label"]),
    )
    return [
        {**app, "models": sorted(app["models"], key=lambda model: model["object_name"].casefold())}
        for app in apps
    ]
