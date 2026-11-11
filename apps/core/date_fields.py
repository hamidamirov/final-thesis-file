from datetime import datetime

from django import forms
from django.utils import timezone

from .ui_text import ui_lazy


class PastOrTodayDatesMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.latest_date = timezone.localdate()
        self.restricted_date_fields = [
            name for name, field in self.fields.items()
            if name != "target_date"
            and isinstance(field, (forms.DateField, forms.DateTimeField, forms.SplitDateTimeField))
        ]
        for name in self.restricted_date_fields:
            widget = self.fields[name].widget
            if isinstance(widget, forms.SplitDateTimeWidget):
                widget = widget.widgets[0]
            widget.attrs["data-latest-date"] = self.latest_date.isoformat()
            if getattr(widget, "input_type", None) == "date":
                widget.attrs["max"] = self.latest_date.isoformat()

    def clean(self):
        cleaned_data = super().clean()
        for name in self.restricted_date_fields:
            value = cleaned_data.get(name)
            if isinstance(value, datetime):
                value = timezone.localdate(value) if timezone.is_aware(value) else value.date()
            if value is not None and value > self.latest_date:
                self.add_error(name, forms.ValidationError(
                    ui_lazy("Choose today or an earlier date."),
                    code="future_date",
                ))
        return cleaned_data


class PastOrTodayDatesAdmin:
    def get_form(self, request, obj=None, change=False, **kwargs):
        form_class = super().get_form(request, obj, change=change, **kwargs)

        class RestrictedDateForm(PastOrTodayDatesMixin, form_class):
            pass

        return RestrictedDateForm
