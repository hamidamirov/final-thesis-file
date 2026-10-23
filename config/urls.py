from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from apps.core.views import database_health
from apps.finance.views import dashboard, signup, transaction_delete, transaction_edit

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/signup/", signup, name="signup"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("transactions/<int:pk>/edit/", transaction_edit, name="transaction_edit"),
    path("transactions/<int:pk>/delete/", transaction_delete, name="transaction_delete"),
    path("", dashboard, name="home"),
    path("health/database/", database_health, name="database_health"),
]
