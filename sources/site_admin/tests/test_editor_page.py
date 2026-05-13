import pytest
from django.test import Client
from django.urls import reverse

from nfc_cards.models import Card


@pytest.fixture
def client():
    return Client()


@pytest.mark.django_db
def test_editor_page_loads_for_unpublished(client):
    card = Card.objects.create(title="", content="")
    r = client.get(reverse("card_editor", kwargs={"token": card.token}))
    assert r.status_code == 200
    cc = (r.get("Cache-Control") or "").lower()
    assert "no-store" in cc or "no-cache" in cc
    body = r.content.decode("utf-8")
    assert "editor-restore-json" in body
    assert "editor-draft-recover" in body
    assert "HexgraphEditorAutosave" in body
