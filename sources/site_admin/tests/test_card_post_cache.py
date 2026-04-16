import pytest
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from nfc_cards.models import Card
from nfc_cards.services import card_post_cache


@pytest.fixture
def client():
    return Client()


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def published_card_no_password():
    return Card.objects.create(
        title="T1",
        content="<p>C1</p>",
        is_published=True,
        published_at=timezone.now(),
        background={"type": "color", "value": "#ffffff"},
    )


@pytest.mark.django_db
def test_cache_created_for_published_card(client, published_card_no_password):
    card = published_card_no_password
    token = card.token
    key = card_post_cache.cache_key_for_card_post(card)

    assert key.startswith(f"card_post:{token}:")
    assert cache.get(key) is None

    r = client.get(reverse("card_entry", kwargs={"token": token}))
    assert r.status_code == 200

    cached = cache.get(key)
    assert cached is not None
    assert isinstance(cached, dict)
    assert cached.get("title") == "T1"
    assert "C1" in (cached.get("content") or "")


@pytest.mark.django_db
def test_second_get_uses_cache_without_rebuilding_context(
    client, published_card_no_password, monkeypatch
):
    card = published_card_no_password
    token = card.token
    url = reverse("card_entry", kwargs={"token": token})

    calls = {"n": 0}
    orig = card_post_cache.build_post_template_context

    def wrapped(c):
        calls["n"] += 1
        return orig(c)

    monkeypatch.setattr(card_post_cache, "build_post_template_context", wrapped)

    r1 = client.get(url)
    assert r1.status_code == 200
    assert calls["n"] == 1

    r2 = client.get(url)
    assert r2.status_code == 200
    assert calls["n"] == 1


@pytest.mark.django_db
def test_password_gate_does_not_write_public_post_cache(client):
    card = Card.objects.create(
        title="Sec",
        content="<p>Hidden</p>",
        is_published=True,
        published_at=timezone.now(),
        view_password_hash=make_password("secret"),
        background={"type": "color", "value": "#eeeeee"},
    )
    token = card.token
    key = card_post_cache.cache_key_for_card_post(card)

    r = client.get(reverse("card_entry", kwargs={"token": token}))
    assert r.status_code == 200
    assert b"post-unlock-page" in r.content
    assert cache.get(key) is None


@pytest.mark.django_db
def test_card_change_uses_new_cache_key(client, published_card_no_password):
    card = published_card_no_password
    token = card.token
    url = reverse("card_entry", kwargs={"token": token})

    r1 = client.get(url)
    assert r1.status_code == 200
    assert b"T1" in r1.content

    key_before = card_post_cache.cache_key_for_card_post(
        Card.objects.get(pk=card.pk)
    )
    assert cache.get(key_before) is not None

    card.title = "T2"
    card.content = "<p>C2</p>"
    card.background = {"type": "color", "value": "#000011"}
    card.save()

    card.refresh_from_db()
    key_after = card_post_cache.cache_key_for_card_post(card)
    assert key_after != key_before

    r2 = client.get(url)
    assert r2.status_code == 200
    assert b"T2" in r2.content
    assert b"C2" in r2.content

    assert cache.get(key_after) is not None
    assert cache.get(key_after).get("title") == "T2"
    assert card_post_cache.get_or_build_post_context(card)["title"] == "T2"
