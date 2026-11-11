from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.db import DatabaseError, connection, transaction
from django.forms import IntegerField, ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import AdminActivityPreferences
from .ui_text import LANGUAGE_OPTIONS


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "core/home.html")


def database_health(request):
    """Report whether the configured database can answer a simple query."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


@require_POST
def save_preferences(request):
    language = request.POST.get("language")
    theme = request.POST.get("theme")
    if language in {code for code, _label in LANGUAGE_OPTIONS}:
        request.session["site_language"] = language
    if theme in {"light", "dark"}:
        request.session["site_theme"] = theme

    return_to = request.POST.get("next", "/")
    if not url_has_allowed_host_and_scheme(
        return_to, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return_to = "/"
    return redirect(return_to)


@require_POST
@transaction.atomic
def manage_admin_activity(request):
    action = request.POST.get("action")
    actions = LogEntry.objects.filter(user=request.user)
    entry_id = None
    if action in {"hide", "delete_entry"}:
        try:
            entry_id = IntegerField(min_value=1, max_value=2**63 - 1).clean(
                request.POST.get("entry_id")
            )
        except ValidationError:
            return redirect("admin:index")
        if not actions.filter(pk=entry_id).exists():
            return redirect("admin:index")
    elif action not in {"clear", "restore", "delete_history"}:
        return redirect("admin:index")

    if action in {"delete_entry", "delete_history"}:
        selected = actions.filter(pk=entry_id) if entry_id else actions
        if request.POST.get("confirm") != "yes":
            return render(request, "admin/activity_delete_confirmation.html", {
                **admin.site.each_context(request),
                "action": action,
                "entry_id": entry_id,
            })
        selected.delete()
        return redirect("admin:index")

    preferences, _ = AdminActivityPreferences.objects.select_for_update().get_or_create(
        user=request.user
    )
    if action == "hide":
        if entry_id > preferences.cleared_through_id and entry_id not in preferences.hidden_action_ids:
            preferences.hidden_action_ids.append(entry_id)
    else:
        preferences.hidden_action_ids = []
        preferences.cleared_through_id = (
            actions.order_by("-pk").values_list("pk", flat=True).first() or 0
            if action == "clear" else 0
        )
    preferences.save(update_fields=["hidden_action_ids", "cleared_through_id"])
    return redirect("admin:index")
