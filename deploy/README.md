# Deploy — инструкция

## Файлы

| Файл | Назначение |
|---|---|
| `setup-vps.sh` | Один раз: настройка чистого VPS (Ubuntu 22.04) |
| `deploy.sh` | Каждый деплой: pull → pip → migrate → restart |
| `cloud-init.yaml` | Timeweb: автозапуск setup-vps.sh при создании сервера |

---

## Вариант A — через Cloud-init (Timeweb, автоматически)

1. Открой `cloud-init.yaml`
2. Замени `ТВОЙ_USER/ТВОЙ_REPO` на реальный путь к репозиторию (GitHub)
3. При создании VPS в Timeweb вставь содержимое `cloud-init.yaml` в поле **«User data»**
4. Создай сервер → он настроится автоматически (~3–5 минут)
5. Подключись по SSH и отредактируй `.env`:

```bash
ssh root@IP_СЕРВЕРА
nano /var/www/app/current/.env
# замени ЗАМЕНИ_НА_ДОМЕН_ИЛИ_IP на IP сервера или домен
```

---

## Вариант B — вручную (любой VPS)

```bash
# 1. Подключись к серверу
ssh root@IP_СЕРВЕРА

# 2. Скачай и запусти скрипт настройки
curl -fsSL https://raw.githubusercontent.com/ТВОЙ_USER/ТВОЙ_REPO/main/deploy/setup-vps.sh | bash

# 3. Или если репо ещё не на GitHub — скопируй скрипт через scp:
scp deploy/setup-vps.sh root@IP_СЕРВЕРА:/root/
ssh root@IP_СЕРВЕРА "bash /root/setup-vps.sh"
```

---

## После настройки VPS — первый деплой

```bash
# 1. Подключись как deploy
ssh deploy@IP_СЕРВЕРА

# 2. Загрузи код (выбери один вариант)

# Вариант: скопировать папку целиком (если нет git)
# На своей машине:
scp -r sources/site_admin deploy@IP:/var/www/app/current/sources/site_admin

# Вариант: git clone (если репо есть)
# В deploy.sh заполни REPO_URL и запусти:
# bash /var/www/app/deploy.sh

# 3. Отредактируй .env
nano /var/www/app/current/.env

# 4. Запусти деплой
bash /var/www/app/deploy.sh

# 5. Проверь
systemctl status app
curl http://localhost/
```

---

## Дальше — SSL (после подключения домена)

```bash
# Замени server_name в nginx конфиге
nano /etc/nginx/sites-available/app
# server_name ваш-домен.ru;

# Получи сертификат
certbot --nginx -d ваш-домен.ru

# Добавь в .env:
# DJANGO_CSRF_TRUSTED_ORIGINS=https://ваш-домен.ru
# DJANGO_SESSION_COOKIE_SECURE=1
# DJANGO_SECURE_SSL_REDIRECT=1
# DJANGO_TRUST_FORWARDED_PROTO=1

# Перезапусти
systemctl restart app
systemctl reload nginx
```

---

## Полезные команды

```bash
# Статус сервиса
systemctl status app

# Логи gunicorn
tail -f /var/www/app/logs/gunicorn-error.log

# Логи nginx
tail -f /var/www/app/logs/nginx-error.log

# Перезапустить без downtime (graceful reload)
systemctl reload app     # или kill -HUP $(cat /run/gunicorn.pid)

# Django shell на сервере
cd /var/www/app/current/sources/site_admin
source /var/www/app/venv/bin/activate
source /var/www/app/current/.env
python manage.py shell
```
