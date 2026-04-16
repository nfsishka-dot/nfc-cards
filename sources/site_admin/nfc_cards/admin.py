from django.contrib import admin
from .models import Card, LinkGroup, Photo, Video


@admin.register(LinkGroup)
class LinkGroupAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "created_at")
    search_fields = ("title",)


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ("id", "token", "link_group", "is_published", "created_at", "published_at", "total_size")
    search_fields = ("token", "title", "author_name")
    list_filter = ("is_published", "created_at")


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ("id", "card", "uploaded_at", "size")


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ("id", "card", "uploaded_at", "size")

