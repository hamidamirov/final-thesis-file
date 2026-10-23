from decimal import Decimal
from datetime import date

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from .forms import BudgetForm, RegistrationForm, TransactionForm
from .models import Budget, Transaction, first_day_of_current_month


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
    if request.method == "POST" and request.POST.get("form_type") == "budget":
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
    elif request.method == "POST":
        form = TransactionForm(request.POST)
        budget_form = BudgetForm(initial={"month": first_day_of_current_month()})
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.user = request.user
            transaction.save()
            messages.success(request, "Transaction added successfully.")
            return redirect("home")
    else:
        form = TransactionForm()
        budget_form = BudgetForm(initial={"month": first_day_of_current_month()})

    user_transactions = Transaction.objects.filter(user=request.user)
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
            "transactions": user_transactions,
            "income_total": income,
            "expense_total": expenses,
            "balance": income - expenses,
            "budget_form": budget_form,
            "budgets": budgets,
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
