# Deploy — инструкция

Полная схема: **[ARCHITECTURE.md](ARCHITECTURE.md)** (PROD_ROOT, git, systemd, nginx).

## Файлы

| Файл | Назначение |
|---|---|
| `setup-vps.sh` | Один раз: настройка чистого VPS (Ubuntu 22.04) |
| `deploy.sh` | Каждый деплой: `git fetch` + `reset --hard origin/main` → pip → migrate → static → `app` → nginx |
| `bootstrap-server.sh` | Первый `git clone` в `/var/www/nfc-cards` (после setup-vps) |
| `fix-systemd-unify-path.sh` | Выровнять systemd под фактический каталог |
| `cloud-init.yaml` | Timeweb: автозапуск setup-vps.sh при создании сервера |
| `../deploy.sh` (корень репозитория) | Обёртка → `deploy/deploy.sh` |
| `../.github/workflows/deploy.yml` | **Production V5:** job `production-deploy-v5` → `deploy/v5-deploy.sh` |
| `v5-deploy.sh` | **Текущий прод-пайплайн:** `shared/.env`, `releases/`, `current`, flock, healthcheck, блок отчёта `DEPLOY STATUS` / `ACTIVE_RELEASE` / `ACTIVE_COMMIT` / `HEALTHCHECK` |
| `v4-deploy.sh` | Без `shared/.env` (только `$BASE/.env`) |
| `v3-deploy.sh` | Один каталог git |

**V5 на сервере:** секреты в **`/var/www/nfc-cards/shared/.env`** (если ещё только `$BASE/.env` — скрипт один раз скопирует в `shared/.env`, строку проверь вручную). **Проверка после деплоя (выполнять на VPS):**

```bash
sudo systemctl status app
curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1/
ls -la /var/www/nfc-cards/current
git -C /var/www/nfc-cards/current rev-parse HEAD
```

**Ручной деплой (если Actions недоступны):** из корня репозитория на сервере: `sudo bash deploy/v5-deploy.sh` (или `bash -s < deploy/v5-deploy.sh` после `scp`/`git pull`).

**GitHub Actions (V5):** Secrets: `SSH_PRIVATE_KEY`, `VPS_HOST`, `VPS_USER`. Успех деплоя = **зелёный job** `production-deploy-v5` **и** блок отчёта в логе SSH-шага **и** проверки выше на VPS.

**Nginx:** пути к статике/медиа через **`/var/www/nfc-cards/current/sources/site_admin/...`** (или `alias` на `shared/media` для media).

---

## Вариант A — через Cloud-init (Timeweb, автоматически)

1. Открой `cloud-init.yaml` и при необходимости обнови URL raw-файлов на GitHub.
2. При создании VPS вставь содержимое в **«User data»**.
3. После загрузки сервера: отредактируй `.env` и выполни первый клон + деплой (см. ниже).

---

## Вариант B — вручную (любой VPS)

```bash
ssh root@IP_СЕРВЕРА
curl -fsSL https://raw.githubusercontent.com/nfsishka-dot/nfc-cards/main/deploy/setup-vps.sh | bash
```

---

## После настройки VPS — первый клон и деплой

```bash
ssh deploy@IP_СЕРВЕРА

# Один раз: клон репозитория (если ещё нет /var/www/nfc-cards/.git)
sudo bash /var/www/nfc-cards/deploy/bootstrap-server.sh
# или вручную: git clone https://github.com/nfsishka-dot/nfc-cards.git /var/www/nfc-cards

# Секреты (не в git)
nano /var/www/nfc-cards/.env
# замени MY_SERVER_IP на IP или домен

# Деплой
sudo bash /var/www/nfc-cards/deploy/deploy.sh

# Проверка
systemctl status app
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1/
```

---

## SSL (после подключения домена)

```bash
nano /etc/nginx/sites-available/app
# server_name ваш-домен.ru;

certbot --nginx -d ваш-домен.ru

# В .env после HTTPS:
# DJANGO_CSRF_TRUSTED_ORIGINS=https://ваш-домен.ru
# DJANGO_SESSION_COOKIE_SECURE=1
# DJANGO_SECURE_SSL_REDIRECT=1
# DJANGO_TRUST_FORWARDED_PROTO=1

systemctl restart app
systemctl reload nginx
```

---

## Старый каталог `/var/www/app`

Если на сервере остался старый деплой — см. **DEPRECATED** в [ARCHITECTURE.md](ARCHITECTURE.md). Скрипт `fix-systemd-unify-path.sh` помогает согласовать systemd и gunicorn без смены кода приложения.

---

## Полезные команды

```bash
systemctl status app
tail -f /var/www/nfc-cards/logs/gunicorn-error.log
tail -f /var/www/nfc-cards/logs/nginx-error.log
systemctl reload app

cd /var/www/nfc-cards/sources/site_admin
source /var/www/nfc-cards/venv/bin/activate
set -a; source /var/www/nfc-cards/.env; set +a
python manage.py shell
```
