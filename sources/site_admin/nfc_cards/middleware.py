"""Rate limit по IP для критичных эндпоинтов (cache-based)."""
from __future__ import annotations

import logging
import re
import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse

from .ip_utils import client_ip_for_request

logger_rl = logging.getLogger("nfc_cards.ratelimit")

_CARD_OP_PATH = re.compile(
    r"^/[^/]+/(?P<op>upload-image|preview|publish)/?$",
    re.IGNORECASE,
)


def _rate_key(bucket: str, ip: str) -> str:
    window = int(time.time() // settings.RATE_LIMIT_WINDOW_SECONDS)
    return f"rl:{bucket}:{ip}:{window}"


def _check_and_incr(bucket: str, ip: str, limit: int) -> bool:
    key = _rate_key(bucket, ip)
    try:
        n = cache.incr(key, delta=1)
    except ValueError:
        cache.add(key, 1, timeout=settings.RATE_LIMIT_WINDOW_SECONDS + 5)
        n = 1
    return n <= limit


class CardEditorRateLimitMiddleware:
    """
    Лимит запросов с одного IP за окно (по умолчанию 25/60 с).
    upload-image — только POST; publish — только POST; preview — GET и POST.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ""
        m = _CARD_OP_PATH.match(path)
        if not m:
            return self.get_response(request)

        op = m.group("op").lower()
        method = request.method.upper()

        if op == "upload-image" and method != "POST":
            return self.get_response(request)
        if op == "publish" and method != "POST":
            return self.get_response(request)

        bucket = {"upload-image": "upload", "preview": "preview", "publish": "publish"}[op]
        limit = getattr(settings, "RATE_LIMIT_PER_MINUTE", 25)
        ip = client_ip_for_request(request)

        if not _check_and_incr(bucket, ip, limit):
            logger_rl.warning(
                "rate_limit exceeded bucket=%s ip=%s path=%s", bucket, ip, path
            )
            if op == "upload-image":
                return JsonResponse(
                    {"error": "rate_limited", "message": "Слишком много запросов. Подождите минуту."},
                    status=429,
                )
            return HttpResponse(
                "Слишком много запросов. Подождите минуту.",
                status=429,
                content_type="text/plain; charset=utf-8",
            )

        return self.get_response(request)
