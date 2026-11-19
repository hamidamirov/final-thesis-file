from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

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


class StudentAuthenticationForm(AuthenticationForm):
    def clean(self):
        identifier = self.cleaned_data.get("username")
        if identifier and "@" in identifier:
            user_model = get_user_model()
            users = user_model._default_manager
            try:
                users.get_by_natural_key(identifier)
            except user_model.DoesNotExist:
                usernames = list(users.filter(email__iexact=identifier).values_list("username", flat=True)[:2])
                if len(usernames) == 1:
                    self.cleaned_data["username"] = usernames[0]
        return super().clean()


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
        widgets = {"target_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}


class GoalContributionForm(forms.Form):
    amount = forms.DecimalField(
        min_value=0.01,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
    )


class TransactionForm(PastOrTodayDatesMixin, forms.ModelForm):
    EXPENSE_CATEGORIES = (
        "Food", "Coffee", "Groceries", "Transport", "Rent", "Utilities",
        "Books", "Shopping", "Health", "Entertainment", "Subscriptions",
    )
    INCOME_CATEGORIES = ("Salary", "Study grant", "Freelance", "Gifts")
    DEFAULT_CATEGORIES = EXPENSE_CATEGORIES + INCOME_CATEGORIES
    CATEGORY_ALIASES = {"yemey": "Food", "yemək": "Food", "qida": "Food"}
    CUSTOM_CATEGORY = "__custom_category__"  # Used only by the category selector.
    category_choice = forms.ChoiceField(required=False, label=ui_lazy("Category"))
    field_order = ["type", "category_choice", "category", "amount", "date", "note"]

    def __init__(self, *args, language="en", categories=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["type"].choices = [
            (value, translate_ui(label, language))
            for value, label in self.fields["type"].choices
        ]
        categories = tuple(categories)
        current = self.initial.get("category")
        while any(name == self.CUSTOM_CATEGORY for _, name in categories) or self.CUSTOM_CATEGORY == current:
            self.CUSTOM_CATEGORY += "_"
        choices = [("", translate_ui("Choose a category", language))]
        self.category_types = {}
        all_presets = {name.casefold() for name in self.DEFAULT_CATEGORIES}
        records = (*categories, (self.initial.get("type"), current))
        for kind, presets in (
            (Transaction.Type.INCOME, self.INCOME_CATEGORIES),
            (Transaction.Type.EXPENSE, self.EXPENSE_CATEGORIES),
        ):
            saved = {
                self.CATEGORY_ALIASES.get(name.casefold(), name).casefold(): name
                for saved_type, name in records if saved_type == kind and name
            }
            typed_choices = [(saved.get(name.casefold(), name), translate_ui(name, language)) for name in presets]
            typed_choices.extend((saved[key], saved[key]) for key in sorted(saved.keys() - all_presets))
            self.category_types[kind] = {value for value, _ in typed_choices}
            choices.append((translate_ui(kind.label, language), typed_choices))
        choices.append((self.CUSTOM_CATEGORY, translate_ui("Add a custom category", language)))
        self.fields["category_choice"].choices = choices
        self.fields["category"].required = False
        self.fields["category"].label = ui_lazy("Custom category")
        available = current in self.category_types.get(self.initial.get("type"), ())
        self.initial["category_choice"] = current if available else self.CUSTOM_CATEGORY if current else ""
        self.initial["category"] = current if current and not available else ""

    def clean(self):
        data = super().clean()
        choice = data.get("category_choice")
        if choice and choice != self.CUSTOM_CATEGORY:
            if choice in self.category_types.get(data.get("type"), ()):
                data["category"] = choice
            elif "type" in data:
                self.add_error("category_choice", ui_lazy("Choose a category for this transaction type."))
        elif "category" in data and not data["category"]:
            field = "category" if choice == self.CUSTOM_CATEGORY else "category_choice"
            self.add_error(field, ui_lazy("Enter a category name." if choice else "Choose a category."))
        return data

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


class AccountDeletionRequestForm(forms.Form):
    reason = forms.CharField(label=ui_lazy("Reason"), max_length=1000, widget=forms.Textarea(attrs={"rows": 4}))


class StudentVerificationForm(forms.Form):
    university = forms.CharField(max_length=180, label=ui_lazy("University"))
    university_email = forms.EmailField(label=ui_lazy("University email"))

    def clean_university_email(self):
        return self.cleaned_data["university_email"].strip().lower()
