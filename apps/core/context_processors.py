from .ui_text import LANGUAGE_OPTIONS


def site_preferences(request):
    language = request.session.get("site_language", "en")
    theme = request.session.get("site_theme", "light")
    if language not in {code for code, _label in LANGUAGE_OPTIONS}:
        language = "en"
    if theme not in {"light", "dark"}:
        theme = "light"
    return {
        "site_language": language,
        "site_theme": theme,
        "language_options": LANGUAGE_OPTIONS,
        "theme_options": [("light", "Light"), ("dark", "Dark")],
    }
