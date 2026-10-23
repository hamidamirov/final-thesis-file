import csv
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    BudgetForm,
    GoalContributionForm,
    RegistrationForm,
    SavingsGoalForm,
    TransactionForm,
)
from .models import (
    Budget,
    FinancialTip,
    SavingChallenge,
    SavingsGoal,
    StudentOffer,
    Transaction,
    UserChallenge,
    first_day_of_current_month,
)


def signup(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        auth_login(request, user)
        return redirect("home")
    return render(request, "registration/signup.html", {"form": form})


@login_required
def dashboard(request):
    if request.method == "POST" and request.POST.get("challenge_action") == "start":
        challenge = get_object_or_404(
            SavingChallenge, pk=request.POST.get("challenge_id"), is_active=True
        )
        UserChallenge.objects.get_or_create(user=request.user, challenge=challenge)
        messages.success(request, f"You joined the {challenge.title} challenge.")
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
            messages.success(request, f"You completed the {enrollment.challenge.title} challenge.")
        return redirect("home")

    form_type = request.POST.get("form_type") if request.method == "POST" else ""
    if form_type == "budget":
        form = TransactionForm()
        budget_form = BudgetForm(request.POST)
        if budget_form.is_valid():
            budget = budget_form.save(commit=False)
            Budget.objects.update_or_create(
                user=request.user,
                category=budget.category,
                month=budget.month,
                defaults={"amount": budget.amount},
            )
            messages.success(request, "Monthly budget saved successfully.")
            return redirect("home")
    elif form_type == "savings_goal":
        form = TransactionForm()
        budget_form = BudgetForm(initial={"month": first_day_of_current_month()})
        goal_form = SavingsGoalForm(request.POST)
        if goal_form.is_valid():
            goal = goal_form.save(commit=False)
            goal.user = request.user
            goal.save()
            messages.success(request, "Savings goal created successfully.")
            return redirect("home")
    elif form_type == "goal_contribution":
        form = TransactionForm()
        budget_form = BudgetForm(initial={"month": first_day_of_current_month()})
        goal_form = SavingsGoalForm()
        contribution_form = GoalContributionForm(request.POST)
        goal = get_object_or_404(
            SavingsGoal, pk=request.POST.get("goal_id"), user=request.user
        )
        if contribution_form.is_valid():
            goal.saved_amount += contribution_form.cleaned_data["amount"]
            goal.save(update_fields=["saved_amount"])
            messages.success(request, f"Progress updated for {goal.name}.")
            return redirect("home")
    elif form_type == "transaction":
        form = TransactionForm(request.POST)
        budget_form = BudgetForm(initial={"month": first_day_of_current_month()})
        goal_form = SavingsGoalForm()
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.user = request.user
            transaction.save()
            messages.success(request, "Transaction added successfully.")
            return redirect("home")
    else:
        form = TransactionForm()
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
    if search_query:
        transaction_list = transaction_list.filter(
            Q(category__icontains=search_query) | Q(note__icontains=search_query)
        )
    if selected_type in Transaction.Type.values:
        transaction_list = transaction_list.filter(type=selected_type)
    if selected_transaction_month:
        try:
            transaction_year_text, transaction_month_text = selected_transaction_month.split(
                "-", maxsplit=1
            )
            transaction_month_start = date(
                int(transaction_year_text), int(transaction_month_text), 1
            )
            if transaction_month_start.month == 12:
                transaction_next_month = date(transaction_month_start.year + 1, 1, 1)
            else:
                transaction_next_month = date(
                    transaction_month_start.year, transaction_month_start.month + 1, 1
                )
            transaction_list = transaction_list.filter(
                date__gte=transaction_month_start,
                date__lt=transaction_next_month,
            )
        except (ValueError, TypeError):
            selected_transaction_month = ""
    totals = user_transactions.aggregate(
        income=Sum("amount", filter=Q(type=Transaction.Type.INCOME)),
        expenses=Sum("amount", filter=Q(type=Transaction.Type.EXPENSE)),
    )
    income = totals["income"] or Decimal("0.00")
    expenses = totals["expenses"] or Decimal("0.00")
    month_start = first_day_of_current_month()
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
    month_value = request.GET.get("month", "")
    try:
        year_text, month_text = month_value.split("-", maxsplit=1)
        report_month = date(int(year_text), int(month_text), 1)
    except (ValueError, TypeError):
        report_month = month_start

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
    month_value = request.GET.get("month", "")
    try:
        year_text, month_text = month_value.split("-", maxsplit=1)
        report_month = date(int(year_text), int(month_text), 1)
    except (ValueError, TypeError):
        report_month = first_day_of_current_month()

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
    if request.method == "POST":
        form = TransactionForm(request.POST, instance=transaction)
        if form.is_valid():
            form.save()
            messages.success(request, "Transaction updated successfully.")
            return redirect("home")
    else:
        form = TransactionForm(instance=transaction)
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
        messages.success(request, "Transaction deleted successfully.")
        return redirect("home")
    return render(request, "finance/transaction_confirm_delete.html", {"transaction": transaction})
