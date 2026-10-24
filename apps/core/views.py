from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

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
