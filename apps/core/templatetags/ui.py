from django import template

from apps.core.ui_text import translate_ui

register = template.Library()


@register.filter
def translate(value, language):
    return translate_ui(value, language)


@register.simple_tag(takes_context=True)
def tr(context, value):
    return translate_ui(value, context.get("site_language", "en"))
