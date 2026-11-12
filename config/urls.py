from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from apps.core.views import database_health, home, manage_admin_activity, save_preferences
from apps.finance.views import (
    budget_delete,
    dashboard,
    monthly_report_csv,
    savings_goal_delete,
    savings_goal_edit,
    signup,
    signup_verify,
    transaction_delete,
    transaction_edit,
)

urlpatterns = [
    path("admin/activity/", admin.site.admin_view(manage_admin_activity), name="manage_admin_activity"),
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path(
        "accounts/password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
            email_template_name="registration/password_reset_email.html",
            subject_template_name="registration/password_reset_subject.txt",
            success_url="/accounts/password-reset/done/",
        ),
        name="password_reset",
    ),
    path(
        "accounts/password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "accounts/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url="/accounts/reset/complete/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "accounts/reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path("accounts/signup/", signup, name="signup"),
    path("accounts/signup/verify/", signup_verify, name="signup_verify"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("dashboard/", dashboard, name="dashboard"),
    path("budgets/<int:pk>/delete/", budget_delete, name="budget_delete"),
    path("savings-goals/<int:pk>/edit/", savings_goal_edit, name="savings_goal_edit"),
    path("savings-goals/<int:pk>/delete/", savings_goal_delete, name="savings_goal_delete"),
    path("transactions/<int:pk>/edit/", transaction_edit, name="transaction_edit"),
    path("transactions/<int:pk>/delete/", transaction_delete, name="transaction_delete"),
    path("reports/monthly.csv", monthly_report_csv, name="monthly_report_csv"),
    path("", home, name="home"),
    path("health/database/", database_health, name="database_health"),
    path("preferences/", save_preferences, name="save_preferences"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
