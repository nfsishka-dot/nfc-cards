from django.urls import path
from .views import (
    add_admin,
    admin_dashboard,
    admin_login,
    admin_logout,
    create_links,
    delete_admin,
    delete_card,
    delete_card_content,
    delete_link_group,
    download_link_group_txt,
    edit_link_group,
    export_csv,
    manage_admins,
    reveal_card_view_password,
)

app_name = "nfc_cards"

urlpatterns = [
    path("", admin_dashboard, name="dashboard"),
    path("login/", admin_login, name="login"),
    path("logout/", admin_logout, name="logout"),
    path("create-links/", create_links, name="create_links"),
    path("link-group/<int:group_id>/edit/", edit_link_group, name="edit_link_group"),
    path("link-group/<int:group_id>/delete/", delete_link_group, name="delete_link_group"),
    path(
        "link-group/<int:group_id>/download-links.txt",
        download_link_group_txt,
        name="download_link_group_txt",
    ),
    path("delete-card-content/<int:card_id>/", delete_card_content, name="delete_card_content"),
    path("delete-card/<int:card_id>/", delete_card, name="delete_card"),
    path(
        "card/<int:card_id>/reveal-view-password/",
        reveal_card_view_password,
        name="reveal_view_password",
    ),
    path("export-csv/", export_csv, name="export_csv"),
    path("admins/", manage_admins, name="manage_admins"),
    path("admins/add/", add_admin, name="add_admin"),
    path("admins/delete/<int:user_id>/", delete_admin, name="delete_admin"),
]
