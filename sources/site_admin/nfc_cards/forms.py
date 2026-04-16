from django import forms
from .models import Card


ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_VIDEO_EXT = {".mp4", ".webm", ".mov"}
MAX_VIDEO_SIZE = 50 * 1024 * 1024


class ContactForm(forms.Form):
    name = forms.CharField(label="Имя", max_length=255)
    phone = forms.CharField(label="Телефон", max_length=50)
    message = forms.CharField(label="Сообщение", widget=forms.Textarea)


class CardEditForm(forms.ModelForm):
    background_color = forms.CharField(
        label="Цвет фона", widget=forms.TextInput(attrs={"type": "color"})
    )
    text_color = forms.CharField(
        label="Цвет текста", widget=forms.TextInput(attrs={"type": "color"})
    )

    external_images_raw = forms.CharField(
        label="Ссылки на изображения (по одной в строке)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    external_videos_raw = forms.CharField(
        label="Ссылки на видео (по одной в строке)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    class Meta:
        model = Card
        fields = ["title", "author_name", "content", "background_color", "text_color"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "w-full text-3xl font-semibold outline-none border-none bg-transparent",
                    "placeholder": "Заголовок...",
                }
            ),
            "author_name": forms.TextInput(
                attrs={
                    "class": "w-full text-sm text-gray-500 outline-none border-none bg-transparent",
                    "placeholder": "Имя автора (необязательно)",
                }
            ),
            "content": forms.Textarea(
                attrs={
                    "class": "w-full min-h-[200px] outline-none border-none bg-transparent",
                    "placeholder": "Ваш текст в Markdown...",
                }
            ),
        }

    def clean(self):
        cleaned = super().clean()
        if self.data.get("publish") and not cleaned.get("title"):
            raise forms.ValidationError("Нельзя опубликовать открытку без заголовка.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)

        images_raw = self.cleaned_data.get("external_images_raw", "")
        videos_raw = self.cleaned_data.get("external_videos_raw", "")

        instance.external_images = [
            line.strip() for line in images_raw.splitlines() if line.strip()
        ]
        instance.external_videos = [
            line.strip() for line in videos_raw.splitlines() if line.strip()
        ]

        if commit:
            instance.save()
        return instance


class MediaUploadForm(forms.Form):
    photos = forms.FileField(
        label="Фото",
        required=False,
        widget=forms.ClearableFileInput(),
    )
    videos = forms.FileField(
        label="Видео",
        required=False,
        widget=forms.ClearableFileInput(),
    )

    def clean_photos(self):
        f = self.files.get("photos")
        if f:
            ext = "." + f.name.lower().rsplit(".", 1)[-1]
            if ext not in ALLOWED_IMAGE_EXT:
                raise forms.ValidationError("Недопустимый формат изображения.")
        return f

    def clean_videos(self):
        f = self.files.get("videos")
        if f:
            ext = "." + f.name.lower().rsplit(".", 1)[-1]
            if ext not in ALLOWED_VIDEO_EXT:
                raise forms.ValidationError("Недопустимый формат видео.")
            if f.size > MAX_VIDEO_SIZE:
                raise forms.ValidationError(f"Видео {f.name} превышает 50 МБ.")
        return f


