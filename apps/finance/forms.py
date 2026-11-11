from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from apps.core.date_fields import PastOrTodayDatesMixin
from apps.core.ui_text import translate_ui, ui_lazy

from .models import Budget, SavingsGoal, StudentProfile, Transaction


class StudentProfileForm(forms.ModelForm):
    profile_picture = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
    )
    remove_profile_picture = forms.BooleanField(required=False)

    class Meta:
        model = StudentProfile
        fields = ["university"]

    def save(self, commit=True):
        profile = super().save(commit=False)
        new_picture = self.cleaned_data.get("profile_picture")
        remove_picture = self.cleaned_data.get("remove_profile_picture")
        old_picture_name = profile.profile_picture.name if profile.profile_picture else ""
        picture_storage = profile._meta.get_field("profile_picture").storage

        if new_picture:
            profile.profile_picture = new_picture
        elif remove_picture:
            profile.profile_picture = ""

        if commit:
            profile.save()
            if old_picture_name and (new_picture or remove_picture):
                picture_storage.delete(old_picture_name)
        return profile


class AccountDetailsForm(forms.ModelForm):
    email = forms.EmailField(required=True, label="Email")

    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name", "email"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        user_model = get_user_model()
        if user_model.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(ui_lazy("An account with this email already exists."))
        return email


class BudgetForm(PastOrTodayDatesMixin, forms.ModelForm):
    class Meta:
        model = Budget
        fields = ["category", "month", "amount"]
        widgets = {"month": forms.DateInput(attrs={"type": "date"})}

    def clean(self):
        cleaned_data = super().clean()
        if "month" in cleaned_data:
            cleaned_data["month"] = cleaned_data["month"].replace(day=1)
        return cleaned_data


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


class TransactionForm(PastOrTodayDatesMixin, forms.ModelForm):
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
            raise forms.ValidationError(ui_lazy("An account with this email already exists."))
        return email


class RegistrationCodeForm(forms.Form):
    code = forms.RegexField(
        regex=r"\A[0-9]{6}\Z",
        label=ui_lazy("Verification code"),
        min_length=6,
        max_length=6,
        error_messages={"invalid": ui_lazy("Enter the six-digit verification code.")},
        widget=forms.TextInput(
            attrs={"inputmode": "numeric", "autocomplete": "one-time-code", "autofocus": True}
        ),
    )
