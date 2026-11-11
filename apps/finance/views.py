import csv
from datetime import date, timedelta
from decimal import Decimal
from secrets import randbelow

from django.contrib import messages
from django.contrib.auth import get_user_model, login as auth_login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import get_connection, send_mail
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.core.ui_text import localize_ui, translate_ui

from .forms import (
    AccountDetailsForm,
    BudgetForm,
    GoalContributionForm,
    RegistrationCodeForm,
    RegistrationForm,
    SavingsGoalForm,
    StudentProfileForm,
    TransactionForm,
)
from .models import (
    Budget,
    FinancialTip,
    PendingRegistration,
    SavingChallenge,
    SavingsGoal,
    StudentProfile,
    StudentOffer,
    Transaction,
    UserChallenge,
    first_day_of_current_month,
)


REGISTRATION_CODE_LIFETIME = timedelta(minutes=2)
REGISTRATION_LOCKOUT = timedelta(minutes=15)
REGISTRATION_RESEND_LIMIT = 3


def _send_registration_code(email, code):
    try:
        return send_mail(
            localize_ui("Verify your StudentBudget email"),
            localize_ui("Your StudentBudget verification code is {code}.", code=code)
            + "\n\n"
            + localize_ui("It expires in 2 minutes. If you did not request this, ignore this email."),
            None,
            [email],
            connection=get_connection(timeout=15),
        )
    except OSError:
        return 0


@transaction.atomic
def _resend_registration_code(pending_id):
    pending = PendingRegistration.objects.select_for_update().filter(pk=pending_id).first()
    if pending is None:
        return "This registration session has expired."

    now = timezone.now()
    if pending.blocked_until and pending.blocked_until > now:
        return "Too many incorrect codes. Wait until the lockout ends."
    if pending.expires_at > now:
        return "Wait for the current code to expire before requesting another."
    if pending.resend_count >= REGISTRATION_RESEND_LIMIT:
        return "You have reached the limit of three new codes."

    code = f"{randbelow(1_000_000):06d}"
    while check_password(code, pending.code_hash):
        code = f"{randbelow(1_000_000):06d}"
    code_hash = make_password(code)
    if not _send_registration_code(pending.email, code):
        return "The new code could not be sent. Please try again."

    pending.code_hash = code_hash
    pending.expires_at = timezone.now() + REGISTRATION_CODE_LIFETIME
    pending.resend_count += 1
    if pending.blocked_until is not None:
        pending.attempts_left = PendingRegistration.ATTEMPT_LIMIT
        pending.blocked_until = None
    pending.save(update_fields=["code_hash", "expires_at", "resend_count", "attempts_left", "blocked_until"])
    return None


def signup(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        now = timezone.now()
        cleanup_before = now - REGISTRATION_LOCKOUT
        PendingRegistration.objects.filter(expires_at__lte=cleanup_before).filter(
            Q(blocked_until__isnull=True) | Q(blocked_until__lte=cleanup_before)
        ).delete()
        code = f"{randbelow(1_000_000):06d}"
        try:
            pending, created = PendingRegistration.objects.get_or_create(
                email=user.email,
                defaults={
                    "username": user.username,
                    "password_hash": user.password,
                    "code_hash": make_password(code),
                    "expires_at": now + REGISTRATION_CODE_LIFETIME,
                },
            )
        except IntegrityError:
            form.add_error(None, localize_ui("Registration could not be started. Please try again."))
        else:
            if not created:
                if request.session.get("pending_registration_id") == pending.pk:
                    return redirect("signup_verify")
                if pending.blocked_until and pending.blocked_until > now:
                    form.add_error("email", localize_ui("Too many incorrect codes. Request a new code after the 15-minute lockout."))
                else:
                    form.add_error("email", localize_ui("A registration is already in progress. Use the original verification page or try again later."))
            else:
                if _send_registration_code(pending.email, code):
                    request.session["pending_registration_id"] = pending.pk
                    return redirect("signup_verify")
                pending.delete()
                form.add_error(None, localize_ui("The verification email could not be sent. Please try again."))
    return render(request, "registration/signup.html", {"form": form})


@never_cache
def signup_verify(request):
    if request.user.is_authenticated:
        return redirect("home")

    pending_id = request.session.get("pending_registration_id")
    pending = PendingRegistration.objects.filter(pk=pending_id).first()
    if pending is None:
        request.session.pop("pending_registration_id", None)
        return redirect("signup")

    is_resend = request.method == "POST" and request.POST.get("action") == "resend"
    resend_error = None
    if is_resend:
        resend_error = _resend_registration_code(pending_id)
        if resend_error is None:
            return redirect("signup_verify")
        pending = PendingRegistration.objects.filter(pk=pending_id).first()
        if pending is None:
            return redirect("signup")

    form = RegistrationCodeForm(request.POST if request.method == "POST" and not is_resend else None)
    user = None
    if request.method == "POST" and not is_resend and form.is_valid():
        user_model = get_user_model()
        try:
            with transaction.atomic():
                pending = PendingRegistration.objects.select_for_update().filter(pk=pending_id).first()
                if pending is None:
                    return redirect("signup")
                now = timezone.now()
                if pending.expires_at <= now or not pending.attempts_left:
                    form.add_error("code", localize_ui("This code is no longer valid."))
                elif not check_password(form.cleaned_data["code"], pending.code_hash):
                    pending.attempts_left -= 1
                    if pending.attempts_left == 0:
                        pending.blocked_until = now + REGISTRATION_LOCKOUT
                    pending.save(update_fields=["attempts_left", "blocked_until"])
                    form.add_error("code", localize_ui("The verification code is incorrect."))
                elif user_model.objects.filter(
                    Q(username=pending.username) | Q(email__iexact=pending.email)
                ).exists():
                    pending.delete()
                    request.session.pop("pending_registration_id", None)
                    return redirect("signup")
                else:
                    user = user_model.objects.create(
                        username=pending.username,
                        email=pending.email,
                        password=pending.password_hash,
                    )
                    pending.delete()
        except IntegrityError:
            user = None
            form.add_error(None, localize_ui("The account could not be created. Start registration again."))

    if user is not None:
        request.session.pop("pending_registration_id", None)
        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("home")

    now = timezone.now()
    is_blocked = pending.blocked_until is not None and pending.blocked_until > now
    available_at = pending.blocked_until if is_blocked else pending.expires_at
    return render(
        request,
        "registration/signup_verify.html",
        {
            "form": form,
            "email": pending.email,
            "can_verify": pending.expires_at > now and pending.attempts_left > 0,
            "is_blocked": is_blocked,
            "remaining_ms": max(0, int((available_at - now).total_seconds() * 1000)),
            "resends_left": REGISTRATION_RESEND_LIMIT - pending.resend_count,
            "can_resend": (
                not is_blocked and pending.expires_at <= now
                and pending.resend_count < REGISTRATION_RESEND_LIMIT
            ),
            "resend_error": resend_error,
        },
    )


def past_or_current_month(value, current_month):
    try:
        year, month = value.split("-", maxsplit=1)
        selected_month = date(int(year), int(month), 1)
    except ValueError:
        return None
    return selected_month if selected_month <= current_month else None


@login_required
def dashboard(request):
    language = request.session.get("site_language", "en")
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    profile_form = StudentProfileForm(instance=profile)
    account_details_form = AccountDetailsForm(instance=request.user)
    password_change_form = PasswordChangeForm(user=request.user)

    if request.method == "POST" and request.POST.get("form_type") == "profile":
        profile_form = StudentProfileForm(
            request.POST, request.FILES, instance=profile
        )
        account_details_form = AccountDetailsForm(request.POST, instance=request.user)
        if profile_form.is_valid() and account_details_form.is_valid():
            profile_form.save()
            account_details_form.save()
            messages.success(request, translate_ui("Profile updated successfully.", language))
            return redirect("/dashboard/#my-profile")

    if request.method == "POST" and request.POST.get("form_type") == "password_change":
        password_change_form = PasswordChangeForm(user=request.user, data=request.POST)
        if password_change_form.is_valid():
            updated_user = password_change_form.save()
            update_session_auth_hash(request, updated_user)
            messages.success(request, translate_ui("Password changed successfully.", language))
            return redirect("/dashboard/#my-profile")

    if request.method == "POST" and request.POST.get("challenge_action") == "start":
        challenge = get_object_or_404(
            SavingChallenge, pk=request.POST.get("challenge_id"), is_active=True
        )
        UserChallenge.objects.get_or_create(user=request.user, challenge=challenge)
        messages.success(
            request,
            translate_ui("You joined the {title} challenge.", language, title=challenge.title),
        )
        return redirect("home")
    if request.method == "POST" and request.POST.get("challenge_action") == "complete":
        enrollment = get_object_or_404(
            UserChallenge,
            pk=request.POST.get("enrollment_id"),
            user=request.user,
            challenge__is_active=True,
        )
        if enrollment.completed_at is None:
            enrollment.completed_at = timezone.now()
            enrollment.save(update_fields=["completed_at"])
            messages.success(
                request,
                translate_ui(
                    "You completed the {title} challenge.",
                    language,
                    title=enrollment.challenge.title,
                ),
            )
        return redirect("home")

    form_type = request.POST.get("form_type") if request.method == "POST" else ""
    if form_type == "budget":
        form = TransactionForm(language=language)
        budget_form = BudgetForm(request.POST)
        if budget_form.is_valid():
            budget = budget_form.save(commit=False)
            Budget.objects.update_or_create(
                user=request.user,
                category=budget.category,
                month=budget.month,
                defaults={"amount": budget.amount},
            )
            messages.success(request, translate_ui("Monthly budget saved successfully.", language))
            return redirect("home")
    elif form_type == "savings_goal":
        form = TransactionForm(language=language)
        budget_form = BudgetForm(initial={"month": first_day_of_current_month()})
        goal_form = SavingsGoalForm(request.POST)
        if goal_form.is_valid():
            goal = goal_form.save(commit=False)
            goal.user = request.user
            goal.save()
            messages.success(request, translate_ui("Savings goal created successfully.", language))
            return redirect("home")
    elif form_type == "goal_contribution":
        form = TransactionForm(language=language)
        budget_form = BudgetForm(initial={"month": first_day_of_current_month()})
        goal_form = SavingsGoalForm()
        contribution_form = GoalContributionForm(request.POST)
        goal = get_object_or_404(
            SavingsGoal, pk=request.POST.get("goal_id"), user=request.user
        )
        if contribution_form.is_valid():
            goal.saved_amount += contribution_form.cleaned_data["amount"]
            goal.save(update_fields=["saved_amount"])
            messages.success(
                request,
                translate_ui("Progress updated for {name}.", language, name=goal.name),
            )
            return redirect("home")
    elif form_type == "transaction":
        form = TransactionForm(request.POST, language=language)
        budget_form = BudgetForm(initial={"month": first_day_of_current_month()})
        goal_form = SavingsGoalForm()
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.user = request.user
            transaction.save()
            messages.success(request, translate_ui("Transaction added successfully.", language))
            return redirect("home")
    else:
        form = TransactionForm(language=language)
        budget_form = BudgetForm(initial={"month": first_day_of_current_month()})
        goal_form = SavingsGoalForm()

    if "goal_form" not in locals():
        goal_form = SavingsGoalForm()
    if "contribution_form" not in locals():
        contribution_form = GoalContributionForm()

    user_transactions = Transaction.objects.filter(user=request.user)
    transaction_list = user_transactions
    search_query = request.GET.get("q", "").strip()
    selected_type = request.GET.get("type", "")
    selected_transaction_month = request.GET.get("transaction_month", "").strip()
    month_start = first_day_of_current_month()
    if search_query:
        transaction_list = transaction_list.filter(
            Q(category__icontains=search_query) | Q(note__icontains=search_query)
        )
    if selected_type in Transaction.Type.values:
        transaction_list = transaction_list.filter(type=selected_type)
    transaction_month = past_or_current_month(selected_transaction_month, month_start)
    if transaction_month:
        transaction_list = transaction_list.filter(
            date__year=transaction_month.year, date__month=transaction_month.month,
        )
        selected_transaction_month = transaction_month.isoformat()[:7]
    else:
        selected_transaction_month = ""
    totals = user_transactions.aggregate(
        income=Sum("amount", filter=Q(type=Transaction.Type.INCOME)),
        expenses=Sum("amount", filter=Q(type=Transaction.Type.EXPENSE)),
    )
    income = totals["income"] or Decimal("0.00")
    expenses = totals["expenses"] or Decimal("0.00")
    budgets = Budget.objects.filter(user=request.user, month=month_start)
    for budget in budgets:
        budget.spent = (
            user_transactions.filter(
                type=Transaction.Type.EXPENSE,
                category__iexact=budget.category,
                date__year=month_start.year,
                date__month=month_start.month,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        budget.remaining = budget.amount - budget.spent

    savings_goals = SavingsGoal.objects.filter(user=request.user)
    for goal in savings_goals:
        goal.progress_percent = min(
            100, round(float(goal.saved_amount / goal.target_amount * 100))
        )
        goal.remaining_amount = max(Decimal("0.00"), goal.target_amount - goal.saved_amount)
    financial_tips = FinancialTip.objects.filter(is_active=True)
    available_offers = StudentOffer.objects.filter(is_active=True).filter(
        Q(valid_until__isnull=True) | Q(valid_until__gte=timezone.localdate())
    )
    offer_categories = list(
        available_offers.order_by("category")
        .values_list("category", flat=True)
        .distinct()
    )
    selected_offer_category = request.GET.get("offer_category", "").strip()
    if selected_offer_category in offer_categories:
        available_offers = available_offers.filter(category=selected_offer_category)
    else:
        selected_offer_category = ""
    saving_challenges = list(SavingChallenge.objects.filter(is_active=True))
    challenge_entries = {
        entry.challenge_id: entry
        for entry in UserChallenge.objects.filter(
            user=request.user, challenge__in=saving_challenges
        )
    }
    for challenge in saving_challenges:
        challenge.user_entry = challenge_entries.get(challenge.pk)

    # A month-specific report, scoped to the signed-in user's transactions.
    report_month = past_or_current_month(request.GET.get("month", ""), month_start) or month_start

    if report_month.month == 12:
        next_month = date(report_month.year + 1, 1, 1)
    else:
        next_month = date(report_month.year, report_month.month + 1, 1)

    report_transactions = user_transactions.filter(
        date__gte=report_month,
        date__lt=next_month,
    )
    report_totals = report_transactions.aggregate(
        income=Sum("amount", filter=Q(type=Transaction.Type.INCOME)),
        expenses=Sum("amount", filter=Q(type=Transaction.Type.EXPENSE)),
    )
    report_income = report_totals["income"] or Decimal("0.00")
    report_expenses = report_totals["expenses"] or Decimal("0.00")

    def category_report(transaction_type):
        rows = list(
            report_transactions.filter(type=transaction_type)
            .values("category")
            .annotate(total=Sum("amount"))
            .order_by("-total", "category")
        )
        largest_total = max((row["total"] for row in rows), default=Decimal("0.00"))
        for row in rows:
            row["bar_width"] = round(float(row["total"] / largest_total * 100), 1)
        return rows

    report_income_categories = category_report(Transaction.Type.INCOME)
    report_expense_categories = category_report(Transaction.Type.EXPENSE)

    return render(
        request,
        "finance/dashboard.html",
        {
            "form": form,
            "transactions": transaction_list,
            "recent_transactions": user_transactions[:5],
            "profile": profile,
            "profile_form": profile_form,
            "account_details_form": account_details_form,
            "password_change_form": password_change_form,
            "search_query": search_query,
            "selected_type": selected_type,
            "selected_transaction_month": selected_transaction_month,
            "transaction_types": Transaction.Type.choices,
            "income_total": income,
            "expense_total": expenses,
            "balance": income - expenses,
            "budget_form": budget_form,
            "budgets": budgets,
            "goal_form": goal_form,
            "contribution_form": contribution_form,
            "savings_goals": savings_goals,
            "financial_tips": financial_tips,
            "student_offers": available_offers,
            "offer_categories": offer_categories,
            "selected_offer_category": selected_offer_category,
            "saving_challenges": saving_challenges,
            "current_month": month_start,
            "report_month": report_month,
            "report_income": report_income,
            "report_expenses": report_expenses,
            "report_balance": report_income - report_expenses,
            "report_income_categories": report_income_categories,
            "report_expense_categories": report_expense_categories,
        },
    )


@login_required
def monthly_report_csv(request):
    month_start = first_day_of_current_month()
    report_month = past_or_current_month(request.GET.get("month", ""), month_start) or month_start

    if report_month.month == 12:
        next_month = date(report_month.year + 1, 1, 1)
    else:
        next_month = date(report_month.year, report_month.month + 1, 1)

    transactions = Transaction.objects.filter(
        user=request.user,
        date__gte=report_month,
        date__lt=next_month,
    ).order_by("date", "created_at")
    totals = transactions.aggregate(
        income=Sum("amount", filter=Q(type=Transaction.Type.INCOME)),
        expenses=Sum("amount", filter=Q(type=Transaction.Type.EXPENSE)),
    )
    income = totals["income"] or Decimal("0.00")
    expenses = totals["expenses"] or Decimal("0.00")

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="finance-report-{report_month:%Y-%m}.csv"'
    )
    response.write("\ufeff")  # Excel recognizes UTF-8 correctly with this marker.
    writer = csv.writer(response)
    writer.writerow(["Monthly Finance Report", report_month.strftime("%B %Y")])
    writer.writerow(["Total income", income])
    writer.writerow(["Total expenses", expenses])
    writer.writerow(["Monthly balance", income - expenses])
    writer.writerow([])
    writer.writerow(["Date", "Type", "Category", "Amount", "Note"])

    def safe_text(value):
        value = str(value or "")
        if value.startswith(("=", "+", "-", "@", "\t", "\r")):
            return "'" + value
        return value

    for transaction in transactions:
        writer.writerow(
            [
                transaction.date.isoformat(),
                transaction.get_type_display(),
                safe_text(transaction.category),
                transaction.amount,
                safe_text(transaction.note),
            ]
        )
    return response


@login_required
def transaction_edit(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk, user=request.user)
    language = request.session.get("site_language", "en")
    if request.method == "POST":
        form = TransactionForm(request.POST, instance=transaction, language=language)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                translate_ui("Transaction updated successfully.", language),
            )
            return redirect("home")
    else:
        form = TransactionForm(instance=transaction, language=language)
    return render(
        request,
        "finance/transaction_form.html",
        {"form": form, "title": "Edit transaction", "button_label": "Save changes"},
    )


@login_required
def transaction_delete(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk, user=request.user)
    if request.method == "POST":
        transaction.delete()
        messages.success(
            request,
            translate_ui(
                "Transaction deleted successfully.",
                request.session.get("site_language", "en"),
            ),
        )
        return redirect("home")
    return render(request, "finance/transaction_confirm_delete.html", {"transaction": transaction})
