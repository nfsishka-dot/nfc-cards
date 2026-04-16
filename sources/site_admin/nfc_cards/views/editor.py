import json
import logging

from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from ..content_limits import human_error_message
from ..models import Card
from ..services import card_flow

log = logging.getLogger("nfc_cards")


def card_editor(request, token):
    card = get_object_or_404(Card, token=token)
    if card.is_published:
        return redirect("card_entry", token=token)

    restore_key = request.GET.get("restore")
    editor_restore = card_flow.build_editor_initial_state(request, card, token, restore_key)
    background_images = card_flow.editor_background_assets()

    return render(
        request,
        "cards/hexgraph/editor.html",
        {
            "card": card,
            "background_images": background_images,
            "background_images_json": json.dumps(background_images, ensure_ascii=False),
            "editor_restore": editor_restore,
        },
    )


@require_POST
def card_save_draft(request, token):
    card = get_object_or_404(Card, token=token)
    status, body = card_flow.save_card_draft_response(request, card, token)
    return JsonResponse(body, status=status)


def card_preview(request, token):
    card = get_object_or_404(Card, token=token)
    if card.is_published:
        return redirect("card_entry", token=token)

    session_key = card_flow.preview_session_key(token)
    if request.method == "POST":
        content = request.POST.get("content") or ""
        title = request.POST.get("title") or ""
        background_raw = request.POST.get("background_value") or ""
        ok, draft_id, err_code = card_flow.create_preview_draft(
            request, card, token, content, title, background_raw
        )
        if not ok:
            messages.error(request, human_error_message(err_code))
            return redirect("card_editor", token=token)
        request.session[session_key] = draft_id
        return redirect("card_preview", token=token)

    ctx = card_flow.load_preview_draft(request, card, token)
    if ctx is None:
        return redirect("card_editor", token=token)
    return render(
        request,
        "cards/hexgraph/preview.html",
        ctx,
    )


def card_finalize(request, token):
    if request.method != "POST":
        raise Http404

    card = get_object_or_404(Card, token=token)
    if card.is_published:
        return redirect("card_entry", token=token)

    out = card_flow.publish_card_from_preview(request, card, token)
    if out.error_human_code:
        messages.error(request, human_error_message(out.error_human_code))
    elif out.error_literal:
        messages.error(request, out.error_literal)
    elif out.success_message:
        messages.success(request, out.success_message)
    return redirect(out.redirect_name, token=token)


def card_restore_editor(request, token):
    card = get_object_or_404(Card, token=token)
    if card.is_published:
        return redirect("card_entry", token=token)

    rid = card_flow.restore_preview_to_editor(request, card, token)
    if rid is None:
        return redirect("card_editor", token=token)
    return redirect(f"{reverse('card_editor', kwargs={'token': token})}?restore={rid}")


@require_http_methods(["GET", "POST"])
def card_deleted(request, token):
    card = get_object_or_404(Card, token=token)
    if request.method == "POST":
        try:
            card.clear_content()
        except Exception:
            log.exception("delete route failed token=%s", token)
            messages.error(request, "Не удалось очистить открытку. Попробуйте снова.")
            return redirect("card_deleted", token=token)
        messages.success(request, "Открытка очищена. Токен сохранён и готов к новой записи.")
        return redirect("card_entry", token=token)
    return render(request, "cards/hexgraph/deleted_confirm.html", {"card": card})
