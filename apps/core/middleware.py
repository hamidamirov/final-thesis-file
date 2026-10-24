from django.utils import translation


LANGUAGE_CODES = {
    "en": "en-us",
    "lt": "lt",
    "az": "az",
}


class SessionLanguageMiddleware:
    """Activate the language selected in the user's session."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        selected_language = request.session.get("site_language", "en")
        if selected_language not in LANGUAGE_CODES:
            selected_language = "en"
            request.session["site_language"] = selected_language
        language_code = LANGUAGE_CODES.get(selected_language, "en-us")
        translation.activate(language_code)
        response = self.get_response(request)
        response.headers["Content-Language"] = language_code
        translation.deactivate()
        return response
