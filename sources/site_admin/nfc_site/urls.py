from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from nfc_cards.views import (
    card_deleted,
    card_editor,
    card_entry,
    card_finalize,
    card_preview,
    card_restore_editor,
    card_save_draft,
    home,
    upload_editor_image,
)

handler404 = "tapnote.views.custom_404"

urlpatterns = [
    path("dj-admin/", admin.site.urls),
    path("", home, name="home"),
    path("adminpanel/", include("nfc_cards.urls")),
    # Важно: до /<token>/, иначе «tapnote» воспринимается как токен карточки.
    path("tapnote/", include("tapnote.urls")),
    path("<str:token>/upload-image/", upload_editor_image, name="card_upload_image"),
    path("<str:token>/edit/", card_editor, name="card_editor"),
    path("<str:token>/save-draft/", card_save_draft, name="card_save_draft"),
    path("<str:token>/preview/", card_preview, name="card_preview"),
    path("<str:token>/publish/", card_finalize, name="card_finalize"),
    path("<str:token>/restore/", card_restore_editor, name="card_restore_editor"),
    path("<str:token>/deleted", card_deleted, name="card_deleted"),
    path("<str:token>/", card_entry, name="card_entry"),
]

if settings.DEBUG or getattr(settings, "SERVE_MEDIA", False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
