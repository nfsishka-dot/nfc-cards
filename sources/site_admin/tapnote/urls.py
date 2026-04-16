from django.urls import path
from . import views

app_name = "tapnote"

urlpatterns = [
    path("", views.home, name="home"),
    path("<str:hashcode>/", views.note_detail, name="note_detail"),
    path("<str:hashcode>/edit/", views.note_edit, name="note_edit"),
]

