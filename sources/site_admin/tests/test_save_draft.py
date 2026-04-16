import json

import pytest
from django.contrib.auth.hashers import check_password
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from nfc_cards.models import Card


@pytest.fixture
def client():
    return Client()


@pytest.mark.django_db
def test_save_draft_updates_unpublished_card(client):
    card = Card.objects.create(title="Old", content="<p>Old</p>")
    token = card.token
    url = reverse("card_save_draft", kwargs={"token": token})
    bg = json.dumps({"type": "color", "value": "#abcdef"}, ensure_ascii=False)

    r = client.post(
        url,
        data={
            "title": "New title",
            "content": "<p>New body</p>",
            "background_value": bg,
            "use_view_password": "0",
            "view_password": "",
            "view_password_confirm": "",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("has_view_password") is False

    card.refresh_from_db()
    assert card.title == "New title"
    assert "New body" in (card.content or "")
    assert card.background.get("value") == "#abcdef"


@pytest.mark.django_db
def test_save_draft_forbidden_when_published(client):
    card = Card.objects.create(
        title="P",
        content="<p>x</p>",
        is_published=True,
        published_at=timezone.now(),
    )
    url = reverse("card_save_draft", kwargs={"token": card.token})
    r = client.post(
        url,
        data={
            "title": "X",
            "content": "<p>y</p>",
            "background_value": '{"type":"color","value":"#fff"}',
            "use_view_password": "0",
        },
    )
    assert r.status_code == 403
    assert r.json().get("error") == "published"


@pytest.mark.django_db
def test_save_draft_single_character_view_password(client):
    card = Card.objects.create(title="T", content="<p>x</p>")
    token = card.token
    url = reverse("card_save_draft", kwargs={"token": token})
    bg = json.dumps({"type": "color", "value": "#ffffff"}, ensure_ascii=False)

    r = client.post(
        url,
        data={
            "title": "T",
            "content": "<p>x</p>",
            "background_value": bg,
            "use_view_password": "1",
            "view_password": "a",
            "view_password_confirm": "a",
        },
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True
    assert r.json().get("has_view_password") is True

    card.refresh_from_db()
    assert card.view_password_hash
    assert check_password("a", card.view_password_hash)


@pytest.mark.django_db
def test_save_draft_rejects_inline_images_data_uri(client):
    card = Card.objects.create(title="T", content="<p>x</p>")
    url = reverse("card_save_draft", kwargs={"token": card.token})
    bg = json.dumps({"type": "color", "value": "#ffffff"}, ensure_ascii=False)
    r = client.post(
        url,
        data={
            "title": "T",
            "content": '<p>x</p><p><img src="data:image/png;base64,AAAA" /></p>',
            "background_value": bg,
            "use_view_password": "0",
        },
    )
    assert r.status_code == 400
    data = r.json()
    assert data.get("ok") is False
    assert "data:" in (data.get("errors", {}).get("_html") or "").lower()


@pytest.mark.django_db
def test_save_draft_rejects_inline_images_blob_uri(client):
    card = Card.objects.create(title="T", content="<p>x</p>")
    url = reverse("card_save_draft", kwargs={"token": card.token})
    bg = json.dumps({"type": "color", "value": "#ffffff"}, ensure_ascii=False)
    r = client.post(
        url,
        data={
            "title": "T",
            "content": '<p>x</p><p><img src="blob:https://example.com/123" /></p>',
            "background_value": bg,
            "use_view_password": "0",
        },
    )
    assert r.status_code == 400
    data = r.json()
    assert data.get("ok") is False
    assert "blob" in (data.get("errors", {}).get("_html") or "").lower()
