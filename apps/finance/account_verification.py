from datetime import timedelta
from secrets import randbelow, token_urlsafe

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import get_connection, send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from apps.core.ui_text import localize_ui

from .models import AccountVerification


CODE_LIFETIME = timedelta(minutes=2)
LOCKOUT = timedelta(minutes=15)


def _digest(value):
    return salted_hmac("studentbudget.account-verification", value, algorithm="sha256").hexdigest()


def _account_hash(user):
    return _digest(f"{user.get_session_auth_hash()}:{user.email}")


def verification_timer(user_id, purpose):
    pending = AccountVerification.objects.filter(user_id=user_id, purpose=purpose).first()
    now = timezone.now()
    is_blocked = bool(pending and pending.blocked_until and pending.blocked_until > now)
    deadline = (pending.blocked_until if is_blocked else pending.expires_at) if pending else now
    return {
        "remaining_ms": max(0, int((deadline - now).total_seconds() * 1000)),
        "is_blocked": is_blocked,
        "can_verify": bool(pending and not is_blocked and pending.attempts_left and deadline > now),
    }


@transaction.atomic
def issue_code(request, authenticated_user, purpose, *, recipient=None):
    user = get_user_model().objects.select_for_update().filter(pk=authenticated_user.pk, is_active=True).first()
    if user is None or not user.email:
        return "This account needs an email address. Contact support."
    if not constant_time_compare(_account_hash(user), _account_hash(authenticated_user)):
        return "Start verification again."
    recipient = recipient or user.email

    pending = AccountVerification.objects.filter(user=user, purpose=purpose).first()
    now = timezone.now()
    browser_token = request.session.get(f"verification_{purpose}")
    if pending:
        if pending.blocked_until and pending.blocked_until > now:
            return "Too many incorrect codes. Try again in 15 minutes."
        if pending.expires_at > now:
            if (browser_token and constant_time_compare(pending.browser_hash, _digest(browser_token))
                    and constant_time_compare(pending.account_hash, _account_hash(user))
                    and (pending.recipient_email or user.email) == recipient):
                return None
            return "A code was recently sent. Wait 2 minutes before trying again."

    code = f"{randbelow(1_000_000):06d}"
    subject = {
        AccountVerification.Purpose.LOGIN: "Your StudentBudget sign-in code",
        AccountVerification.Purpose.DELETION: "Confirm your StudentBudget deletion request",
        AccountVerification.Purpose.EMAIL: "Confirm your StudentBudget email change",
        AccountVerification.Purpose.STUDENT: "Verify your university email",
    }[purpose]
    try:
        sent = send_mail(
            localize_ui(subject),
            localize_ui("Your StudentBudget verification code is {code}.", code=code)
            + "\n\n" + localize_ui("It expires in 2 minutes. If you did not request this, ignore this email."),
            None, [recipient], connection=get_connection(timeout=15),
        )
    except OSError:
        sent = 0
    if not sent:
        return "The verification email could not be sent. Please try again."

    browser_token = token_urlsafe(32)
    AccountVerification.objects.update_or_create(user=user, purpose=purpose, defaults={
        "browser_hash": _digest(browser_token),
        "code_hash": make_password(_digest(code)),
        "account_hash": _account_hash(user),
        "expires_at": timezone.now() + CODE_LIFETIME,
        "attempts_left": 5,
        "blocked_until": None,
        "recipient_email": recipient,
    })
    request.session[f"verification_{purpose}"] = browser_token
    return None


@transaction.atomic
def verify_code(request, user_id, purpose, code, *, recipient=None):
    user = get_user_model().objects.select_for_update().filter(pk=user_id, is_active=True).first()
    pending = AccountVerification.objects.filter(user=user, purpose=purpose).first() if user else None
    browser_token = request.session.get(f"verification_{purpose}")
    if (not pending or not browser_token
            or not constant_time_compare(pending.browser_hash, _digest(browser_token))
            or (recipient is not None and pending.recipient_email != recipient)
            or not constant_time_compare(pending.account_hash, _account_hash(user))):
        return None, "Start verification again."
    if pending.blocked_until and pending.blocked_until > timezone.now():
        return None, "Too many incorrect codes. Try again in 15 minutes."
    if pending.expires_at <= timezone.now() or not pending.attempts_left:
        return None, "This code is no longer valid."
    if not check_password(_digest(code), pending.code_hash):
        pending.attempts_left -= 1
        if not pending.attempts_left:
            pending.blocked_until = timezone.now() + LOCKOUT
        pending.save(update_fields=["attempts_left", "blocked_until"])
        return None, "The verification code is incorrect."

    pending.delete()
    request.session.pop(f"verification_{purpose}", None)
    return user, None
