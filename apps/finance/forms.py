from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from apps.core.ui_text import translate_ui

from .models import Budget, SavingsGoal, Transaction


class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ["category", "month", "amount"]
        widgets = {"month": forms.DateInput(attrs={"type": "date"})}

    def clean_month(self):
        return self.cleaned_data["month"].replace(day=1)


class SavingsGoalForm(forms.ModelForm):
    class Meta:
        model = SavingsGoal
        fields = ["name", "target_amount", "target_date"]
        widgets = {"target_date": forms.DateInput(attrs={"type": "date"})}


class GoalContributionForm(forms.Form):
    amount = forms.DecimalField(
        min_value=0.01,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
    )


class TransactionForm(forms.ModelForm):
    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["type"].choices = [
            (value, translate_ui(label, language))
            for value, label in self.fields["type"].choices
        ]

    class Meta:
        model = Transaction
        fields = ["type", "category", "amount", "date", "note"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = get_user_model()
        fields = ["username", "email"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email
