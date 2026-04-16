from django import template
from django.utils.safestring import mark_safe
import markdown

register = template.Library()


@register.filter
def render_markdown(value):
    if not value:
        return ""
    html = markdown.markdown(
        value,
        extensions=["fenced_code", "codehilite", "tables", "toc"],
        output_format="html5",
    )
    return mark_safe(html)

