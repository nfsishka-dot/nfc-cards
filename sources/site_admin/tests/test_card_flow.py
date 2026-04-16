import json

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from nfc_cards.html_sanitize import sanitize_post_html
from nfc_cards.models import Card, PreviewDraft, Photo
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.hashers import make_password
from PIL import Image
from io import BytesIO


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def unpublished_card():
    return Card.objects.create(title="", content="")


@pytest.fixture
def published_card():
    c = Card.objects.create(
        title="Hello",
        content="<p>Body</p>",
        is_published=True,
        published_at=timezone.now(),
    )
    return c


@pytest.mark.django_db
def test_preview_publish_happy_path(client, unpublished_card):
    token = unpublished_card.token
    bg = json.dumps({"type": "color", "value": "#ffffff"}, ensure_ascii=False)

    r1 = client.post(
        reverse("card_preview", kwargs={"token": token}),
        data={
            "content": "<p>Preview text</p>",
            "title": "My title",
            "background_value": bg,
        },
    )
    assert r1.status_code == 302
    assert PreviewDraft.objects.filter(card=unpublished_card).exists()

    r2 = client.get(reverse("card_preview", kwargs={"token": token}))
    assert r2.status_code == 200

    r3 = client.post(reverse("card_finalize", kwargs={"token": token}), data={})
    assert r3.status_code == 302

    unpublished_card.refresh_from_db()
    assert unpublished_card.is_published is True
    assert unpublished_card.published_at is not None
    assert unpublished_card.title == "My title"
    assert "Preview text" in (unpublished_card.content or "")
    assert not PreviewDraft.objects.filter(card=unpublished_card).exists()


@pytest.mark.django_db
def test_publish_failure_does_not_lose_preview_draft(client, unpublished_card, monkeypatch):
    token = unpublished_card.token
    bg = json.dumps({"type": "color", "value": "#ffffff"}, ensure_ascii=False)

    r1 = client.post(
        reverse("card_preview", kwargs={"token": token}),
        data={"content": "<p>Preview text</p>", "title": "My title", "background_value": bg},
    )
    assert r1.status_code == 302
    assert PreviewDraft.objects.filter(card=unpublished_card).count() == 1

    orig_save = Card.save

    def boom(self, *args, **kwargs):
        if self.pk == unpublished_card.pk and kwargs.get("update_fields") and "is_published" in kwargs["update_fields"]:
            raise Exception("db error")
        return orig_save(self, *args, **kwargs)

    monkeypatch.setattr(Card, "save", boom)

    r2 = client.post(reverse("card_finalize", kwargs={"token": token}), data={})
    assert r2.status_code == 302
    # Draft должен остаться, чтобы пользователь мог повторить publish.
    assert PreviewDraft.objects.filter(card=unpublished_card).count() == 1
    unpublished_card.refresh_from_db()
    assert unpublished_card.is_published is False


@pytest.mark.django_db
def test_card_entry_unpublished_redirects_to_edit(client, unpublished_card):
    r = client.get(reverse("card_entry", kwargs={"token": unpublished_card.token}))
    assert r.status_code == 302
    assert f"/{unpublished_card.token}/edit/" in r.url


@pytest.mark.django_db
def test_card_entry_published_renders_post(client, published_card):
    r = client.get(reverse("card_entry", kwargs={"token": published_card.token}))
    assert r.status_code == 200
    assert b"Body" in r.content


@pytest.mark.django_db
def test_upload_image_forbidden_when_published(client, published_card):
    r = client.post(
        reverse("card_upload_image", kwargs={"token": published_card.token}),
        data={},
    )
    assert r.status_code == 403
    data = r.json()
    assert data.get("error") == "published"


@pytest.mark.django_db
def test_upload_image_success(client, unpublished_card):
    im = Image.new("RGB", (8, 8), color=(255, 0, 0))
    buf = BytesIO()
    im.save(buf, format="PNG")
    buf.seek(0)
    f = SimpleUploadedFile("x.png", buf.getvalue(), content_type="image/png")
    r = client.post(reverse("card_upload_image", kwargs={"token": unpublished_card.token}), data={"file": f})
    assert r.status_code == 200
    data = r.json()
    assert data.get("url")
    assert Photo.objects.filter(card=unpublished_card).count() == 1


@pytest.mark.django_db
def test_upload_image_invalid_image(client, unpublished_card):
    f = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
    r = client.post(reverse("card_upload_image", kwargs={"token": unpublished_card.token}), data={"file": f})
    assert r.status_code == 400
    assert r.json().get("error") == "invalid_image"


@pytest.mark.django_db
def test_upload_image_big_png_success(client, unpublished_card):
    # Регрессия: большой PNG (~3MB+) должен проходить, если не превышены лимиты bytes/pixels.
    im = Image.new("RGBA", (900, 900), color=(0, 0, 0, 0))
    # Добавим шум, чтобы PNG был «тяжёлым»
    px = im.load()
    for y in range(0, 900, 3):
        for x in range(0, 900, 3):
            px[x, y] = ((x * y) % 256, (x * 7 + y * 3) % 256, (x * 13 + y * 11) % 256, (x + y) % 256)
    buf = BytesIO()
    # Компрессию не выкручиваем: хотим «живой» размер файла, близкий к реальности.
    im.save(buf, format="PNG", optimize=False, compress_level=0)
    raw = buf.getvalue()
    assert len(raw) > 3_000_000

    f = SimpleUploadedFile("big.png", raw, content_type="image/png")
    r = client.post(reverse("card_upload_image", kwargs={"token": unpublished_card.token}), data={"file": f})
    assert r.status_code == 200
    data = r.json()
    assert data.get("url")
    assert Photo.objects.filter(card=unpublished_card).count() == 1


@pytest.mark.django_db
def test_password_unlock_flow(client):
    card = Card.objects.create(
        title="Sec",
        content="<p>Body</p>",
        is_published=True,
        published_at=timezone.now(),
        view_password_hash=make_password("secret"),
        background={"type": "color", "value": "#ffffff"},
    )
    url = reverse("card_entry", kwargs={"token": card.token})

    r1 = client.get(url)
    assert r1.status_code == 200
    assert b"post-unlock-page" in r1.content

    r2 = client.post(url, data={"view_password": "wrong"})
    assert r2.status_code == 200
    assert b"\xd0\x9d\xd0\xb5\xd0\xb2\xd0\xb5\xd1\x80\xd0\xbd\xd1\x8b\xd0\xb9 \xd0\xbf\xd0\xb0\xd1\x80\xd0\xbe\xd0\xbb\xd1\x8c" in r2.content

    r3 = client.post(url, data={"view_password": "secret"})
    assert r3.status_code == 302
    # cookie выставлен и повторный GET открывает пост без unlock-страницы
    r4 = client.get(url)
    assert r4.status_code == 200
    assert b"post-unlock-page" not in r4.content


def test_sanitize_post_html_strips_script():
    raw = '<p>ok</p><script>alert(1)</script>'
    out = sanitize_post_html(raw)
    assert "<script" not in out.lower()
    assert "alert" not in out


def test_validate_post_html_rejects_inline_images():
    from nfc_cards.content_limits import validate_post_html

    assert validate_post_html('<p><img src="data:image/png;base64,AAAA"/></p>') == "inline_images_not_allowed"
    assert validate_post_html('<p><img src="blob:https://x/1"/></p>') == "inline_images_not_allowed"
