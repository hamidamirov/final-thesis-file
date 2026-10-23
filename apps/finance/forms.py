from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import Budget, Transaction


class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ["category", "month", "amount"]
        widgets = {"month": forms.DateInput(attrs={"type": "date"})}

    def clean_month(self):
        return self.cleaned_data["month"].replace(day=1)


class TransactionForm(forms.ModelForm):
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
