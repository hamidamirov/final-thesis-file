from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import render


def home(request):
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
