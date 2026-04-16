# NFC-открытки (nfc_cards)

## Установка (Windows)

1. Установи Python 3.10+.
2. В папке проекта выполни:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Миграции и суперпользователь

```bash
python manage.py migrate
python manage.py createsuperuser
```

Суперадмин может:

- заходить в стандартную админку `/dj-admin/`;
- заходить в кастомную панель `/adminpanel/`;
- управлять администраторами на `/adminpanel/admins/`.

## Запуск (разработка)

```bash
DJANGO_DEBUG=1 python manage.py runserver
```

Открой:

- Главная: `http://127.0.0.1:8000/`
- Админ-панель: `http://127.0.0.1:8000/adminpanel/`
- Django admin: `http://127.0.0.1:8000/dj-admin/`

## Production deploy

### Обязательные переменные окружения

| Переменная | Описание |
|---|---|
| `DJANGO_SECRET_KEY` | Непустой случайный ключ. Генерация: `python -c "import secrets; print(secrets.token_urlsafe(64))"`. Без него сервер **не стартует** при `DEBUG=0`. |
| `DJANGO_ALLOWED_HOSTS` | Домены через запятую, например `example.com,www.example.com`. |
| `DATABASE_URL` | PostgreSQL DSN, например `postgres://user:pass@host/db`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | HTTPS origins, например `https://example.com`. |
| `REDIS_URL` | Redis DSN (обязателен при `DJANGO_PRODUCTION=1`). |

### Media-файлы (загруженные изображения)

Без настройки раздачи `/media/` пользователи увидят 404 вместо картинок.

**Вариант A — маленький трафик / staging (Django раздаёт сам):**

```bash
DJANGO_SERVE_MEDIA=1
```

**Вариант B — production (рекомендуется, через nginx):**

```nginx
location /media/ {
    alias /app/media/;
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

### Минимальный production-старт

```bash
export DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')"
export DJANGO_ALLOWED_HOSTS="example.com"
export DATABASE_URL="postgres://..."
export DJANGO_CSRF_TRUSTED_ORIGINS="https://example.com"
export DJANGO_SERVE_MEDIA=1          # или настрой nginx (вариант B)
python manage.py migrate
gunicorn nfc_site.wsgi:application --bind 0.0.0.0:8000
```

## Работа с ссылками NFC

1. Зайди в `/adminpanel/` под админом (`is_staff`).
2. Нажми «Создать ссылки», введи количество (например, 100).
3. Скачай CSV для записи ссылок на брелки.
4. По адресу `/<token>`:
   - если открытка ещё не опубликована — откроется редактор (как Telegra.ph);
   - после публикации — страница просмотра.

