import calendar
from datetime import date, timedelta
from urllib.parse import urlencode

from django import forms
from django.utils import timezone

from apps.core.ui_text import ui_lazy


class DateRangeForm(forms.Form):
    start_date = forms.DateField(
        required=False, label=ui_lazy("Start date"),
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    end_date = forms.DateField(
        required=False, label=ui_lazy("End date"),
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    period = forms.ChoiceField(required=False, choices=(
        ("", ui_lazy("Custom dates")),
        ("today", ui_lazy("Today")),
        ("week", ui_lazy("Last 7 days")),
        ("fortnight", ui_lazy("Last 14 days")),
        ("month", ui_lazy("This month")),
    ))

    def __init__(self, query, *, prefix=None, month_key=None, default_month=False):
        today = timezone.localdate()
        field_prefix = f"{prefix}-" if prefix else ""
        data = {name: query.get(name, "") for name in (
            f"{field_prefix}start_date", f"{field_prefix}end_date", f"{field_prefix}period",
        )}
        explicit_range = any(name in query for name in data)
        if not explicit_range:
            month = today.replace(day=1) if default_month else None
            value = query.get(month_key, "") if month_key else ""
            if value:
                try:
                    requested_month = date.fromisoformat(f"{value}-01")
                    if requested_month <= today:
                        month = requested_month
                except ValueError:
                    pass
            if month:
                data[f"{field_prefix}start_date"] = month.isoformat()
                month_end = month.replace(day=calendar.monthrange(month.year, month.month)[1])
                data[f"{field_prefix}end_date"] = min(today, month_end).isoformat()
        super().__init__(data=data, prefix=prefix)
        self.today = today
        for name in ("start_date", "end_date"):
            self.fields[name].widget.attrs["max"] = today.isoformat()
        self.is_valid()
        if self.is_valid():
            for name in ("start_date", "end_date"):
                value = self.cleaned_data[name]
                self.data[f"{field_prefix}{name}"] = value.isoformat() if value else ""

    def clean(self):
        cleaned = super().clean()
        preset = cleaned.get("period")
        if preset:
            cleaned["end_date"] = self.today
            starts = {
                "today": self.today,
                "week": self.today - timedelta(days=6),
                "fortnight": self.today - timedelta(days=13),
                "month": self.today.replace(day=1),
            }
            cleaned["start_date"] = starts[preset]
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if bool(start) != bool(end):
            raise forms.ValidationError(ui_lazy("Choose both a start date and an end date."))
        if start and end:
            if start > end:
                raise forms.ValidationError(ui_lazy("The start date must be on or before the end date."))
            if end > self.today:
                raise forms.ValidationError(ui_lazy("Choose today or an earlier date."))
        return cleaned

    def filter(self, queryset):
        if not self.is_valid():
            return queryset.none()
        start = self.cleaned_data["start_date"]
        end = self.cleaned_data["end_date"]
        return queryset.filter(date__range=(start, end)) if start else queryset

    @property
    def export_query(self):
        return urlencode({
            name: value.isoformat() if value else ""
            for name, value in self.cleaned_data.items() if name in ("start_date", "end_date")
        })
