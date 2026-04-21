# Production architecture — single source of truth

**Цель:** GitHub (`main`) → VPS (один каталог) → `venv` → Gunicorn (systemd `app`) → Nginx → домен.

Бизнес-логика Django и шаблоны в этом документе не описываются — только деплой.

---

## 1. CURRENT STATE (заполнить на сервере)

Снять факты на VPS и вписать (или приложить вывод команд):

| Поле | Значение |
|------|----------|
| PROD_PATH (cwd gunicorn master) | `readlink -f /proc/$(pgrep -f 'gunicorn.*nfc_site' \| head -1)/cwd` |
| Процесс gunicorn | `ps auxww \| grep gunicorn` |
| venv (exe) | `readlink -f /proc/<PID>/exe` |
| systemd | `systemctl status app` — MainPID совпадает с gunicorn? |
| nginx upstream | `grep -R proxy_pass /etc/nginx/sites-enabled/` |

Пока не выполнен аудит на сервере, строки выше остаются **неподтверждёнными**.

---

## 2. Единая истина (целевая схема репозитория)

| Имя | Путь |
|-----|------|
| **PROD_ROOT** | `/var/www/nfc-cards` |
| **Git remote** | `https://github.com/nfsishka-dot/nfc-cards.git` |
| **Ветка production** | `main` |
| **Django root (manage.py)** | `PROD_ROOT/sources/site_admin` |
| **venv** | `PROD_ROOT/venv` |
| **Секреты** | `PROD_ROOT/.env` (не в git) |
| **Логи** | `PROD_ROOT/logs/` |
| **Совместимость** | `PROD_ROOT/current` → symlink на `.` (старые пути вида `.../current/...`) |

Структура:

```text
/var/www/nfc-cards/
├── .git
├── .env
├── current -> .
├── deploy/
├── venv/
├── logs/
└── sources/
    └── site_admin/     # Django: manage.py, nfc_site.wsgi
```

---

## 3. DEPRECATED (не удалять без явного решения)

Следующие пути считаются **устаревшими** относительно документации в этом репозитории. Физическое удаление каталогов на VPS выполняет только владелец после бэкапа и проверки.

| Путь | Статус |
|------|--------|
| `/var/www/app` и `/var/www/app/current` | **DEPRECATED** — старая схема в документах до унификации; перенос на `PROD_ROOT` вручную или через `git clone` + копирование `.env` |
| Дублирующие `git clone` вне `PROD_ROOT` | **DEPRECATED** — держать один clone |

---

## 4. Деплой (одна команда после настройки)

На сервере:

```bash
sudo bash /var/www/nfc-cards/deploy/deploy.sh
```

Скрипт: `git fetch` → `git reset --hard origin/main` → `pip install` → `migrate` → `collectstatic` → остановка «ручных» gunicorn с `nfc_site.wsgi` → `systemctl restart app` → `nginx reload`.

Короткая обёртка из корня репозитория:

```bash
sudo bash deploy.sh
```

---

## 5. Systemd

- Юнит: `app.service`
- `WorkingDirectory`: `PROD_ROOT/sources/site_admin`
- `ExecStart`: `/usr/local/bin/app-start.sh` (gunicorn `nfc_site.wsgi:application`, unix-сокет)
- Пользователь: `deploy`
- `Restart=always` (в актуальных шаблонах `setup-vps.sh` и `fix-systemd-unify-path.sh`)

Первичная генерация unit: `deploy/setup-vps.sh`. Выровнять уже работающий сервер: `deploy/fix-systemd-unify-path.sh`.

---

## 6. Nginx

- `upstream gunicorn_app` → `unix:/run/gunicorn.sock` (как в `setup-vps.sh`)
- Статика/медиа: alias на `${DJANGO_ROOT}/staticfiles/` и `.../media/`
- После смены путей на сервере: `nginx -t && systemctl reload nginx`

---

## 7. A) FINAL ARCHITECTURE (целевая)

| | |
|--|--|
| **PROD_ROOT** | `/var/www/nfc-cards` |
| **Git branch** | `main` |
| **Gunicorn** | systemd `app` → `nfc_site.wsgi:application` |
| **Venv** | `/var/www/nfc-cards/venv` |

## B) DEPLOY FLOW (одна строка)

GitHub (`main`) → `git clone` / `deploy.sh` на VPS → Gunicorn → Nginx → домен.

## C) PROBLEMS FIXED (в репозитории)

- Единый `PROD_ROOT` и `deploy.sh` с `git reset --hard origin/main`
- `setup-vps.sh` и systemd-шаблоны переведены на `/var/www/nfc-cards` и `.env` в корне репо
- Symlink `current` для обратной совместимости
- `fix-systemd-unify-path.sh`: `Restart=always`

## D) REMAINING RISKS (реальные)

- Пока на VPS не выполнен деплой из этого репозитория, **старые каталоги и процессы могут остаться** — нужен ручной аудит (раздел 1).
- `git reset --hard` сотрёт локальные незакоммиченные правки **на сервере** внутри clone — секреты только в `.env` (в `.gitignore`).
- Без рабочего SSH-ключа автоматизация с локальной машины недоступна.

---

👉 **DEPLOY SYSTEM IS NOW SINGLE-SOURCE-OF-TRUTH** (как **целевая модель в репозитории**; факт на VPS подтверждается только командами из раздела 1).
