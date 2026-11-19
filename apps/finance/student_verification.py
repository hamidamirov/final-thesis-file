from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters

from apps.core.ui_text import localize_ui

from .account_verification import issue_code, verification_timer, verify_code
from .forms import RegistrationCodeForm, StudentVerificationForm
from .models import AccountVerification, StudentProfile, StudentVerificationRequest


def latest_student_request(user):
    return StudentVerificationRequest.objects.filter(user=user).first()


def can_access_student_offers(profile, student_request):
    return bool(
        profile.account_type == StudentProfile.AccountType.STUDENT
        and student_request
        and student_request.status == StudentVerificationRequest.Status.APPROVED
    )


@login_required
@never_cache
@sensitive_post_parameters("code")
@transaction.atomic
def request_student_verification(request):
    user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
    profile, _ = StudentProfile.objects.get_or_create(user=user)
    current = latest_student_request(user)
    if current and current.status in (
        StudentVerificationRequest.Status.PENDING, StudentVerificationRequest.Status.APPROVED,
    ):
        return redirect(f"{reverse('dashboard')}#my-profile")

    draft_key = "pending_student_verification"
    draft = request.session.get(draft_key)
    action = request.POST.get("action")
    details = StudentVerificationForm(
        request.POST if request.method == "POST" and action == "send" else None,
        initial={"university": profile.university, "university_email": profile.university_email},
    )
    code_form = None
    if request.method == "POST":
        if action == "restart":
            request.session.pop(draft_key, None)
            return redirect("request_student_verification")
        if action == "send" and details.is_valid():
            error = issue_code(
                request, user, AccountVerification.Purpose.STUDENT,
                recipient=details.cleaned_data["university_email"],
            )
            if error:
                details.add_error(None, localize_ui(error))
            else:
                request.session[draft_key] = details.cleaned_data
                return redirect("request_student_verification")
        if action == "verify" and draft:
            code_form = RegistrationCodeForm(request.POST)
            if code_form.is_valid():
                verified_user, error = verify_code(
                    request, user.pk, AccountVerification.Purpose.STUDENT,
                    code_form.cleaned_data["code"], recipient=draft["university_email"],
                )
                if verified_user:
                    StudentVerificationRequest.objects.create(
                        user=user, university=draft["university"],
                        university_email=draft["university_email"], email_verified_at=timezone.now(),
                    )
                    profile.account_type = StudentProfile.AccountType.STUDENT
                    profile.university_email = draft["university_email"]
                    profile.save(update_fields=["account_type", "university_email"])
                    request.session.pop(draft_key, None)
                    messages.success(request, localize_ui("Your student status request was sent for administrator review."))
                    return redirect(f"{reverse('dashboard')}#my-profile")
                code_form.add_error("code", localize_ui(error))
    if draft:
        return render(request, "registration/account_verify.html", {
            "form": code_form if code_form is not None else RegistrationCodeForm(),
            "title": "Verify your university email",
            "verification_message": "Enter the six-digit code sent to your university email. The code expires in 2 minutes.",
            "action": "verify",
            "submit_label": "Submit request",
            **verification_timer(user.pk, AccountVerification.Purpose.STUDENT),
        })
    return render(request, "finance/student_verification.html", {"form": details})
