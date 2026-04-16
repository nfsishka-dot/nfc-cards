# План сращивания Django + Hexgraph

## 1) Что берем из админки (source of truth)

- Генерация токенов: `sources/site_admin/nfc_cards/models.py` (`Card.token`).
- Статус публикации и даты: `Card.is_published`, `Card.published_at`.
- Админ-панель и статистика: `nfc_cards/views.py`, `adminpanel/*`.
- Точка входа по NFC: `/<token>/` (`card_entry`).

## 2) Что берем из Hexgraph

- UX редактора Quill: `templates/index.html` + `static/css/styles.css` + `static/js/colorPicker.js`.
- Preview flow:
  - `POST /preview`
  - `GET /preview`
  - `POST /finalize_post`
  - `GET /restore_editor`
- Фон/стили/адаптив + модалка подтверждения публикации.

## 3) Рекомендуемая интеграция в Django

Добавить в `nfc_cards` новые view:

- `card_editor(request, token)`
- `card_preview_post(request, token)`
- `card_preview_get(request, token)`
- `card_finalize(request, token)`
- `card_restore_editor(request, token)`

И обновить `card_entry`:

- если `card.is_published == False`: redirect на `card_editor`;
- иначе render `cards/view.html` (или unified view).

## 4) Хранение preview-черновика

Не хранить большой HTML в cookie session.

Вариант A (предпочтительный): отдельная модель `CardDraftPreview` (FK на Card, TTL).
Вариант B: cache backend (Redis/file-based) по ключу `preview:{user_or_token}:{uuid}`.

## 5) Сопоставление полей

Перенести в `Card` (или related model):

- `content_html` (из Hexgraph `content`)
- `background_json` (`{"type": "color|image", "value": "..."}`)
- возможно `editor_title`

Текущие `title/content` в `Card` можно переиспользовать, но лучше явно назвать поля под HTML-редактор.

## 6) URL-контракт для NFC

- `GET /<token>/` > авто-роут в editor или published view.
- `GET /<token>/edit/`
- `POST /<token>/preview/`
- `GET /<token>/preview/`
- `POST /<token>/publish/`
- `GET /<token>/restore/`

## 7) Проверка сценария

1. В админке создать ссылку.
2. Открыть `/<token>/` -> редактор.
3. Ввести контент/фон/изображения.
4. Нажать «Создать открытку» -> preview.
5. Нажать «Вернуться в редактор» -> состояние сохранено.
6. Нажать «Сохранить» -> модалка подтверждения.
7. «Подтверждаю» -> publish.
8. Повторно открыть `/<token>/` -> только просмотр открытки.

## 8) Риски

- Разные стеки (Flask vs Django) -> нужен перенос шаблонов и JS, а не проксирование.
- Размер HTML и медиа -> не использовать cookie-session для черновиков.
- Безопасность HTML -> оставить sanitize/bleach policy на publish.
