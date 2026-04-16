import logging
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.cache import cache
from django.db.models import Count, Prefetch
from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from ..ip_utils import client_ip_for_request
from ..models import Card, LinkGroup
from ..utils import card_public_host_path, export_cards_csv
from ..view_password_vault import decrypt_view_password

User = get_user_model()
log = logging.getLogger("nfc_cards")
audit = logging.getLogger("nfc_cards.audit")
logger_rl = logging.getLogger("nfc_cards.ratelimit")


def is_staff_user(user):
    return user.is_authenticated and user.is_staff


def is_superadmin(user):
    return user.is_authenticated and user.is_superuser


CREATE_LINKS_MAX_PER_REQUEST = 10_000


def _admin_login_fail_window() -> int:
    return int(time.time() // 60)


def _admin_login_fail_cache_key(ip: str) -> str:
    return f"admin_login_fail:{ip}:{_admin_login_fail_window()}"


def _admin_login_fail_count(ip: str) -> int:
    return int(cache.get(_admin_login_fail_cache_key(ip)) or 0)


def _admin_login_fail_incr(ip: str) -> int:
    key = _admin_login_fail_cache_key(ip)
    try:
        return cache.incr(key)
    except ValueError:
        cache.add(key, 1, timeout=120)
        return 1


def admin_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("nfc_cards:dashboard")

    if request.method == "POST":
        ip = client_ip_for_request(request)
        limit = int(getattr(settings, "ADMIN_LOGIN_RATE_LIMIT_PER_MINUTE", 25) or 25)
        if _admin_login_fail_count(ip) >= limit:
            logger_rl.warning("admin_login rate_limited ip=%s", ip)
            messages.error(request, "Неверный логин или пароль.")
            return render(request, "adminpanel/login.html")

        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_staff:
            cache.delete(_admin_login_fail_cache_key(ip))
            login(request, user)
            return redirect("nfc_cards:dashboard")
        _admin_login_fail_incr(ip)
        messages.error(request, "Неверный логин или пароль.")

    return render(request, "adminpanel/login.html")


@ensure_csrf_cookie
@login_required
@user_passes_test(is_staff_user)
def admin_dashboard(request):
    link_groups = (
        LinkGroup.objects.annotate(card_count=Count("cards", distinct=True))
        .prefetch_related(
            Prefetch(
                "cards",
                queryset=Card.objects.order_by("id").only(
                    "id",
                    "token",
                    "is_published",
                    "published_at",
                    "total_size",
                    "view_password_hash",
                    "view_password_cipher",
                    "link_group_id",
                ),
            )
        )
        .order_by("-created_at")
    )
    legacy_cards = (
        Card.objects.filter(link_group__isnull=True)
        .order_by("id")
        .only(
            "id",
            "token",
            "is_published",
            "published_at",
            "total_size",
            "view_password_hash",
            "view_password_cipher",
            "link_group_id",
        )
    )
    return render(
        request,
        "adminpanel/dashboard.html",
        {
            "link_groups": link_groups,
            "legacy_cards": legacy_cards,
        },
    )


@login_required
@user_passes_test(is_staff_user)
def create_links(request):
    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        if not title:
            messages.error(request, "Укажите название группы.")
            return redirect("nfc_cards:dashboard")
        if len(title) > 255:
            messages.error(request, "Название слишком длинное (максимум 255 символов).")
            return redirect("nfc_cards:dashboard")

        count_raw = request.POST.get("count")
        try:
            count = int(count_raw)
            if count <= 0:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, "Введите корректное положительное число.")
            return redirect("nfc_cards:dashboard")

        if count > CREATE_LINKS_MAX_PER_REQUEST:
            messages.error(
                request,
                f"За один раз можно создать не более {CREATE_LINKS_MAX_PER_REQUEST} ссылок.",
            )
            return redirect("nfc_cards:dashboard")

        lg = LinkGroup.objects.create(title=title)
        Card.objects.bulk_create(
            [Card(link_group=lg, title="") for _ in range(count)]
        )
        audit.info(
            "create_links group_id=%s title=%r count=%s user_id=%s ip=%s",
            lg.id,
            title[:200],
            count,
            request.user.id,
            client_ip_for_request(request),
        )
        messages.success(request, f"Группа «{title}»: создано ссылок: {count}.")
        return redirect("nfc_cards:dashboard")
    raise Http404


@login_required
@user_passes_test(is_staff_user)
@require_POST
def edit_link_group(request, group_id):
    group = get_object_or_404(LinkGroup, id=group_id)
    new_title = (request.POST.get("title") or "").strip()
    if not new_title:
        messages.error(request, "Укажите название группы.")
        return redirect("nfc_cards:dashboard")
    if len(new_title) > 255:
        messages.error(request, "Название слишком длинное (максимум 255 символов).")
        return redirect("nfc_cards:dashboard")
    group.title = new_title
    group.save(update_fields=["title"])
    messages.success(request, "Название группы обновлено.")
    return redirect("nfc_cards:dashboard")


@login_required
@user_passes_test(is_staff_user)
@require_POST
def delete_link_group(request, group_id):
    group = get_object_or_404(LinkGroup, id=group_id)
    label = group.title
    gid = group.id
    group.delete()
    audit.info(
        "delete_link_group group_id=%s title=%r user_id=%s ip=%s",
        gid,
        (label or "")[:200],
        request.user.id,
        client_ip_for_request(request),
    )
    messages.success(request, f"Группа «{label}» и все входящие ссылки удалены.")
    return redirect("nfc_cards:dashboard")


@login_required
@user_passes_test(is_staff_user)
def download_link_group_txt(request, group_id):
    group = get_object_or_404(LinkGroup, id=group_id)
    cards = group.cards.order_by("id").only("id", "token")
    slug = (slugify(group.title) or "").strip("-")[:80]
    if not slug:
        slug = str(group.id)
    filename = f"group-{slug}-{group.id}-links.txt"
    host = request.get_host()

    def line_iter():
        for c in cards.iterator(chunk_size=5000):
            # Не меняем механику ссылок: те же host + /<token>
            yield f"{host}/{c.token}\n"

    audit.info(
        "download_link_group_txt group_id=%s user_id=%s ip=%s",
        group.id,
        request.user.id,
        client_ip_for_request(request),
    )
    response = StreamingHttpResponse(line_iter(), content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Accel-Buffering"] = "no"
    return response


@login_required
@user_passes_test(is_staff_user)
def delete_card_content(request, card_id):
    card = get_object_or_404(Card, id=card_id)
    if request.method == "POST":
        cid = card.id
        card.clear_content()
        audit.info(
            "delete_card_content card_id=%s user_id=%s ip=%s",
            cid,
            request.user.id,
            client_ip_for_request(request),
        )
        messages.success(request, f"Контент открытки №{card.id} удалён.")
    return redirect("nfc_cards:dashboard")


@login_required
@user_passes_test(is_staff_user)
def delete_card(request, card_id):
    card = get_object_or_404(Card, id=card_id)
    if request.method == "POST":
        cid = card.id
        card.clear_content()
        card.delete()
        audit.info(
            "delete_card card_id=%s user_id=%s ip=%s",
            cid,
            request.user.id,
            client_ip_for_request(request),
        )
        messages.success(request, f"Ссылка №{card_id} удалена.")
    return redirect("nfc_cards:dashboard")


@login_required
@user_passes_test(is_staff_user)
@require_POST
def reveal_card_view_password(request, card_id):
    """Возвращает пароль просмотра в JSON только для персонала (для копирования в буфер)."""
    card = get_object_or_404(Card, id=card_id)
    if not (card.view_password_cipher or "").strip():
        return JsonResponse({"ok": False, "error": "no_backup"}, status=404)
    try:
        password = decrypt_view_password(card.view_password_cipher)
    except ImportError:
        return JsonResponse(
            {"ok": False, "error": "no_crypto", "detail": "Установите пакет cryptography на сервере."},
            status=503,
        )
    except Exception:
        log.exception("reveal_card_view_password decrypt card_id=%s", card_id)
        return JsonResponse({"ok": False, "error": "decrypt"}, status=500)
    audit.info(
        "reveal_view_password card_id=%s user_id=%s ip=%s",
        card.id,
        request.user.id,
        client_ip_for_request(request),
    )
    return JsonResponse({"ok": True, "password": password})


@login_required
@user_passes_test(is_staff_user)
def export_csv(request):
    cards = Card.objects.all()
    from_id_raw = (request.GET.get("from_id") or "").strip()
    to_id_raw = (request.GET.get("to_id") or "").strip()

    if from_id_raw or to_id_raw:
        try:
            from_id = int(from_id_raw) if from_id_raw else None
            to_id = int(to_id_raw) if to_id_raw else None
        except ValueError:
            messages.error(request, "Укажите корректный диапазон номеров для CSV.")
            return redirect("nfc_cards:dashboard")

        if from_id is not None and from_id <= 0:
            messages.error(request, "Начальный номер должен быть больше 0.")
            return redirect("nfc_cards:dashboard")
        if to_id is not None and to_id <= 0:
            messages.error(request, "Конечный номер должен быть больше 0.")
            return redirect("nfc_cards:dashboard")
        if from_id is not None and to_id is not None and from_id > to_id:
            messages.error(request, "Начальный номер не может быть больше конечного.")
            return redirect("nfc_cards:dashboard")

        if from_id is not None:
            cards = cards.filter(id__gte=from_id)
        if to_id is not None:
            cards = cards.filter(id__lte=to_id)

    audit.info(
        "export_csv from_id=%s to_id=%s user_id=%s ip=%s",
        from_id_raw or None,
        to_id_raw or None,
        request.user.id,
        client_ip_for_request(request),
    )
    return export_cards_csv(cards, request)


@login_required
@user_passes_test(is_superadmin)
def manage_admins(request):
    admins = User.objects.filter(is_staff=True).order_by("id")
    return render(request, "adminpanel/manage_admins.html", {"admins": admins})


@login_required
@user_passes_test(is_superadmin)
def add_admin(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        if not username or not password:
            messages.error(request, "Укажите логин и пароль.")
            return redirect("nfc_cards:manage_admins")
        if User.objects.filter(username=username).exists():
            messages.error(request, "Пользователь с таким логином уже существует.")
            return redirect("nfc_cards:manage_admins")

        user = User.objects.create_user(username=username, password=password)
        user.is_staff = True
        user.save()
        messages.success(request, "Администратор создан.")
        return redirect("nfc_cards:manage_admins")
    raise Http404


@login_required
@user_passes_test(is_superadmin)
def delete_admin(request, user_id):
    admin_user = get_object_or_404(User, id=user_id, is_staff=True)
    if request.method == "POST":
        if admin_user.is_superuser:
            messages.error(request, "Нельзя удалить суперадмина.")
        else:
            uid = admin_user.id
            uname = admin_user.username
            admin_user.delete()
            audit.info(
                "delete_admin target_user_id=%s target_username=%r actor_id=%s ip=%s",
                uid,
                uname,
                request.user.id,
                client_ip_for_request(request),
            )
            messages.success(request, "Администратор удалён.")
    return redirect("nfc_cards:manage_admins")


@login_required
def admin_logout(request):
    logout(request)
    return redirect("nfc_cards:login")
