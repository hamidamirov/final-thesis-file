from django.core.exceptions import ValidationError

from .ui_text import ui_lazy


class PasswordCompositionValidator:
    def validate(self, password, user=None):
        requirements = (
            (str.isupper, "Include at least one uppercase letter."),
            (str.isdecimal, "Include at least one digit."),
            (lambda character: not character.isalnum() and character.isprintable()
             and not character.isspace(), "Include at least one special character."),
        )
        errors = [
            ValidationError(ui_lazy(message), code="password_composition")
            for matches, message in requirements if not any(map(matches, password))
        ]
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return ui_lazy("Include an uppercase letter, a digit, and a special character.")
