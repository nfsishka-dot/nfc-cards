import logging
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.http.multipartparser import MultiPartParserError
from django.core.exceptions import RequestDataTooBig
from PIL import Image

from ..content_limits import human_error_message, validate_card_total_storage
from ..image_processing import optimize_editor_image
from ..models import Card, Photo

log = logging.getLogger("nfc_cards")


@require_POST
def upload_editor_image(request, token):
    card = get_object_or_404(Card, token=token)
    if card.is_published:
        log.warning("upload rejected published token=%s", token)
        return JsonResponse({"error": "published"}, status=403)

    try:
        f = request.FILES.get("file")
    except RequestDataTooBig:
        log.warning("upload rejected request_too_big token=%s", token)
        return JsonResponse(
            {
                "error": "file_too_large",
                "message": "Файл слишком большой для загрузки. Попробуйте уменьшить размер изображения.",
            },
            status=413,
        )
    except MultiPartParserError as ex:
        log.warning("upload multipart_parse_failed token=%s err=%s", token, ex)
        return JsonResponse({"error": "invalid_upload"}, status=400)
    if not f:
        return JsonResponse({"error": "empty"}, status=400)

    max_b = getattr(settings, "EDITOR_IMAGE_MAX_BYTES", 5 * 1024 * 1024)
    max_px = getattr(settings, "EDITOR_IMAGE_MAX_PIXELS", 24_000_000)
    hard_max_px = getattr(settings, "EDITOR_IMAGE_HARD_MAX_PIXELS", 80_000_000)
    max_edge = getattr(settings, "EDITOR_IMAGE_MAX_EDGE", 1920)
    if f.size > max_b:
        log.warning("upload rejected file_too_large token=%s", token)
        return JsonResponse({"error": "file_too_large"}, status=400)

    raw = f.read()
    try:
        im = Image.open(BytesIO(raw))
        im.verify()
        im = Image.open(BytesIO(raw))
        im.load()
        fmt = (im.format or "").upper()
        if fmt not in ("JPEG", "PNG", "WEBP", "GIF"):
            log.warning("upload rejected format token=%s fmt=%s", token, fmt)
            return JsonResponse({"error": "unsupported_format"}, status=400)
        w, h = im.size
        if w <= 0 or h <= 0:
            log.warning("upload rejected invalid dimensions token=%s", token)
            return JsonResponse({"error": "image_too_large"}, status=400)
        if w * h > hard_max_px:
            log.warning("upload rejected pixels token=%s", token)
            return JsonResponse({"error": "image_too_large"}, status=400)
    except Exception as ex:
        log.warning("upload invalid_image token=%s err=%s", token, ex)
        return JsonResponse({"error": "invalid_image"}, status=400)

    try:
        optimized, suffix = optimize_editor_image(raw, max_edge=max_edge, max_pixels=max_px)
    except Exception:
        log.exception("upload optimize failed token=%s", token)
        return JsonResponse({"error": "processing_failed"}, status=500)

    st_err = validate_card_total_storage(card, card.content or "", len(optimized))
    if st_err:
        log.warning("upload rejected storage token=%s code=%s", token, st_err)
        return JsonResponse({"error": st_err, "message": human_error_message(st_err)}, status=413)

    try:
        photo = Photo(card=card)
        photo.file.save(f"editor{suffix}", ContentFile(optimized), save=False)
        photo.save()
    except Exception:
        log.exception("upload save failed token=%s", token)
        return JsonResponse({"error": "save_failed"}, status=500)

    rel = photo.file.url
    if rel.startswith(("http://", "https://")):
        abs_url = rel
    else:
        abs_url = request.build_absolute_uri(rel)

    return JsonResponse({"url": abs_url})
