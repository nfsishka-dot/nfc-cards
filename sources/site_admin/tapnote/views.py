from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.conf import settings

import markdown
import bleach

from .models import Note


COOKIE_PREFIX = "tapnote_edit_"


ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    "p",
    "pre",
    "code",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "img",
]
ALLOWED_ATTRIBUTES = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title"],
}


def render_markdown_safe(text: str) -> str:
    """Рендер Markdown в HTML + безопасная очистка и правки ссылок."""
    if not text:
        return ""
    raw_html = markdown.markdown(
        text,
        extensions=["fenced_code", "codehilite", "tables"],
        output_format="html5",
    )
    # приведение ссылок: target="_blank" и rel="noopener noreferrer"
    # делаем простую текстовую замену
    raw_html = raw_html.replace("<a ", '<a target="_blank" rel="noopener noreferrer" ')

    cleaned = bleach.clean(
        raw_html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True,
    )
    return cleaned


@require_http_methods(["GET", "POST"])
def home(request):
    if request.method == "POST":
        content = request.POST.get("content", "").strip()
        if not content:
            return render(request, "tapnote/home.html", {"error": "Напишите что‑нибудь перед публикацией."})

        note = Note.objects.create(content=content)
        response = redirect("tapnote:note_detail", hashcode=note.hashcode)
        cookie_name = COOKIE_PREFIX + note.hashcode
        _cookie_secure = bool(getattr(settings, "SESSION_COOKIE_SECURE", False))
        response.set_cookie(
            cookie_name,
            note.edit_token,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            secure=_cookie_secure,
            samesite="Lax",
        )
        return response

    return render(request, "tapnote/home.html")


def _can_edit(request, note: Note) -> bool:
    cookie_name = COOKIE_PREFIX + note.hashcode
    cookie_token = request.COOKIES.get(cookie_name)
    url_token = request.GET.get("token")
    return bool(
        (cookie_token and cookie_token == note.edit_token)
        or (url_token and url_token == note.edit_token)
    )


def note_detail(request, hashcode: str):
    note = get_object_or_404(Note, hashcode=hashcode)
    html = render_markdown_safe(note.content)
    can_edit = _can_edit(request, note)
    return render(
        request,
        "tapnote/detail.html",
        {
            "note": note,
            "html": html,
            "can_edit": can_edit,
        },
    )


@require_http_methods(["GET", "POST"])
def note_edit(request, hashcode: str):
    note = get_object_or_404(Note, hashcode=hashcode)
    cookie_name = COOKIE_PREFIX + note.hashcode
    token = (
        request.GET.get("token")
        or request.POST.get("token")
        or request.COOKIES.get(cookie_name)
    )
    if not token or token != note.edit_token:
        raise Http404()

    if request.method == "POST":
        content = request.POST.get("content", "").strip()
        if not content:
            return render(
                request,
                "tapnote/edit.html",
                {"note": note, "error": "Текст не может быть пустым.", "content": content, "token": token},
            )
        note.content = content
        note.save(update_fields=["content"])
        return redirect("tapnote:note_detail", hashcode=note.hashcode)

    return render(request, "tapnote/edit.html", {"note": note, "content": note.content, "token": note.edit_token})


def custom_404(request, exception=None):
    response = render(request, "tapnote/404.html", status=404)
    return response

