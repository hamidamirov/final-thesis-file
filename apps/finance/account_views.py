from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET

from apps.core.ui_text import localize_ui

from .account_verification import issue_code, verification_timer, verify_code
from .forms import AccountDeletionRequestForm, RegistrationCodeForm, StudentAuthenticationForm
from .models import AccountDeletionRequest, AccountVerification


def latest_deletion_request(user):
    return AccountDeletionRequest.objects.filter(user=user, hidden_from_profile=False).first()


@login_required
@never_cache
@require_GET
def account_deletion_status(request):
    if request.user.is_staff or request.user.is_superuser:
        return HttpResponseRedirect(reverse("dashboard"))
    return render(request, "includes/account_deletion_status.html", {
        "deletion_request": latest_deletion_request(request.user),
    })


class EmailVerificationLoginView(LoginView):
    authentication_form = StudentAuthenticationForm

    def form_valid(self, form):
        user = form.get_user()
        error = issue_code(self.request, user, AccountVerification.Purpose.LOGIN)
        if error:
            form.add_error(None, localize_ui(error))
            return self.form_invalid(form)
        self.request.session.cycle_key()
        self.request.session["pending_login"] = {
            "user_id": user.pk,
            "backend": user.backend,
            "next": self.get_success_url(),
        }
        return redirect("login_verify")


@never_cache
@sensitive_post_parameters("code")
@transaction.atomic
def login_verify(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    pending = request.session.get("pending_login")
    if not pending:
        return redirect("login")

    form = RegistrationCodeForm(request.POST if request.method == "POST" else None)
    if form.is_bound and form.is_valid():
        user, error = verify_code(request, pending["user_id"], AccountVerification.Purpose.LOGIN, form.cleaned_data["code"])
        if user:
            request.session.pop("pending_login", None)
            login(request, user, backend=pending["backend"])
            return HttpResponseRedirect(pending["next"])
        form.add_error("code", localize_ui(error))
    return render(request, "registration/account_verify.html", {
        "form": form,
        "title": "Verify your sign-in",
        "back_url": reverse("login"),
        "back_label": "Back to login",
        "submit_label": "Verify",
        **verification_timer(pending["user_id"], AccountVerification.Purpose.LOGIN),
    })


@login_required
@never_cache
@sensitive_post_parameters("code")
@transaction.atomic
def verify_email_change(request):
    profile_url = f"{reverse('dashboard')}#my-profile"
    new_email = request.session.get("pending_profile_email")
    if not new_email:
        return redirect(profile_url)

    form = RegistrationCodeForm(request.POST if request.method == "POST" else None)
    if form.is_bound and form.is_valid():
        user, error = verify_code(request, request.user.pk, AccountVerification.Purpose.EMAIL, form.cleaned_data["code"])
        if user:
            request.session.pop("pending_profile_email", None)
            if get_user_model().objects.filter(email__iexact=new_email).exclude(pk=user.pk).exists():
                messages.error(request, localize_ui("An account with this email already exists."))
            else:
                user.email = new_email
                user.save(update_fields=["email"])
                messages.success(request, localize_ui("Email address updated."))
            return redirect(profile_url)
        form.add_error("code", localize_ui(error))
    return render(request, "registration/account_verify.html", {
        "form": form,
        "title": "Confirm email address change",
        "back_url": profile_url,
        "back_label": "My profile",
        "submit_label": "Verify",
        **verification_timer(request.user.pk, AccountVerification.Purpose.EMAIL),
    })


@login_required
@never_cache
@sensitive_post_parameters("code")
@transaction.atomic
def request_account_deletion(request):
    profile_url = f"{reverse('dashboard')}#my-profile"
    user = get_user_model().objects.select_for_update().filter(pk=request.user.pk, is_active=True).first()
    if not user or user.is_staff or user.is_superuser:
        return redirect(profile_url)

    pending = AccountDeletionRequest.objects.filter(user=user, status=AccountDeletionRequest.Status.PENDING).first()
    draft_key = "account_deletion_reason"
    code_form = None
    reason_form = AccountDeletionRequestForm(
        request.POST if request.method == "POST" and request.POST.get("action") == "send" else None
    )
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "remove":
            request_id = request.POST.get("request_id", "")
            if request_id.isascii() and request_id.isdigit() and len(request_id) <= 18:
                AccountDeletionRequest.objects.filter(user=user, pk=request_id, status__in=(
                    AccountDeletionRequest.Status.DECLINED, AccountDeletionRequest.Status.CANCELLED,
                )).update(hidden_from_profile=True)
            return redirect(profile_url)
        if pending and action == "cancel":
            pending.status = AccountDeletionRequest.Status.CANCELLED
            pending.save(update_fields=["status"])
            return redirect(profile_url)
        if pending:
            return redirect("request_account_deletion")
        if action == "restart":
            request.session.pop(draft_key, None)
            return redirect("request_account_deletion")
        if action == "send" and reason_form.is_valid():
            error = issue_code(request, request.user, AccountVerification.Purpose.DELETION)
            if error:
                reason_form.add_error(None, localize_ui(error))
            else:
                request.session[draft_key] = reason_form.cleaned_data["reason"]
                return redirect("request_account_deletion")
        if action == "verify" and request.session.get(draft_key):
            code_form = RegistrationCodeForm(request.POST)
            if code_form.is_valid():
                verified_user, error = verify_code(request, user.pk, AccountVerification.Purpose.DELETION, code_form.cleaned_data["code"])
                if verified_user:
                    AccountDeletionRequest.objects.create(
                        user=user, username=user.get_username(), reason=request.session.pop(draft_key)
                    )
                    return redirect(profile_url)
                code_form.add_error("code", localize_ui(error))
    if not pending and request.session.get(draft_key):
        return render(request, "registration/account_verify.html", {
            "form": code_form if code_form is not None else RegistrationCodeForm(),
            "title": "Request account deletion",
            "action": "verify",
            "submit_label": "Submit request",
            **verification_timer(user.pk, AccountVerification.Purpose.DELETION),
        })
    return render(request, "finance/request_account_deletion.html", {
        "pending": pending,
        "reason_form": reason_form,
        "back_url": profile_url,
    })
