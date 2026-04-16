import csv
from urllib.parse import urlparse

from django.http import HttpResponse, StreamingHttpResponse
from django.urls import reverse


def card_public_host_path(request, card):
    """Публичная ссылка как в CSV (build_absolute_uri + card_entry), без схемы http/https."""
    rel = reverse("card_entry", kwargs={"token": card.token})
    p = urlparse(request.build_absolute_uri(rel))
    path = (p.path or "").rstrip("/")
    return f"{p.netloc}{path}" if path else p.netloc


def export_cards_csv(cards_queryset, request):
    """Публичные ссылки на открытки — всегда от корня сайта (имя reverse card_entry)."""
    class _Echo:
        def write(self, value):
            return value

    host = request.get_host()
    # Для CSV-экспорта важна схема (http/https), поэтому берём базу из build_absolute_uri.
    base = request.build_absolute_uri("/")[:-1]

    def row_iter():
        yield "\ufeff"
        writer = csv.writer(_Echo(), delimiter=";")
        yield writer.writerow(["№", "Ссылка"])
        qs = cards_queryset.order_by("id").only("id", "token")
        for card in qs.iterator(chunk_size=2000):
            rel = reverse("card_entry", kwargs={"token": card.token})
            url = f"{base}{rel}"
            yield writer.writerow([card.id, url])

    response = StreamingHttpResponse(row_iter(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="cards.csv"'
    response["X-Accel-Buffering"] = "no"
    return response

