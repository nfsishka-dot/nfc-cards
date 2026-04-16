import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import check_password
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render

from ..card_view_lock import set_unlock_cookie, verify_unlock_cookie
from ..forms import ContactForm
from ..models import Card
from ..services import card_post_cache

log = logging.getLogger("nfc_cards")


def home(request):
    contact_form = ContactForm(request.POST or None)
    if request.method == "POST" and contact_form.is_valid():
        data = contact_form.cleaned_data
        subject = f"Запрос с сайта NFC-открыток от {data['name']}"
        body = (
            f"Имя: {data['name']}\n"
            f"Телефон: {data['phone']}\n\n"
            f"Сообщение:\n{data['message']}"
        )
        try:
            send_mail(
                subject,
                body,
                settings.DEFAULT_FROM_EMAIL,
                [settings.ADMIN_CONTACT_EMAIL],
                fail_silently=False,
            )
        except Exception:
            log.exception("contact_form send_mail failed to=%s", settings.ADMIN_CONTACT_EMAIL)
            messages.error(
                request,
                "Не удалось отправить сообщение. Попробуйте позже или свяжитесь с нами другим способом.",
            )
            return render(request, "home.html", {"contact_form": contact_form})

        messages.success(request, "Сообщение отправлено. Мы свяжемся с вами.")
        return redirect("home")

    return render(request, "home.html", {"contact_form": contact_form})


def card_entry(request, token):
    card = get_object_or_404(Card, token=token)
    if not card.is_published:
        return redirect("card_editor", token=token)

    if card.view_password_hash and not verify_unlock_cookie(request, card):
        if request.method == "POST":
            pw = request.POST.get("view_password") or ""
            if check_password(pw, card.view_password_hash):
                response = redirect("card_entry", token=token)
                set_unlock_cookie(response, card)
                return response
            messages.error(request, "Неверный пароль")
        return render(
            request,
            "cards/hexgraph/post_unlock.html",
            {
                "card": card,
                "title_hint": card.title or "Открытка",
            },
        )

    ctx = card_post_cache.get_or_build_post_context(card)
    return render(request, "cards/hexgraph/post.html", ctx)


def custom_404(request, exception):
    return render(request, "404.html", status=404)
