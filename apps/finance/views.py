from decimal import Decimal

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
