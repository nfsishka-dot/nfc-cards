#!/usr/bin/env bash
# =============================================================================
#  setup-vps.sh — однократная настройка VPS под nfc_cards (Ubuntu 22.04)
#
#  Запуск:  sudo bash setup-vps.sh
#  Повторный запуск безопасен (идемпотентен).
# =============================================================================
set -euo pipefail

# ─── цвета ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

[[ $EUID -ne 0 ]] && error "Запусти скрипт от root: sudo bash $0"

# =============================================================================
# 0. Настраиваемые переменные — менять только здесь
# =============================================================================
APP_USER="deploy"
APP_DIR="/var/www/app"

# Путь внутри репозитория / загруженного кода где лежит manage.py
DJANGO_SUBDIR="sources/site_admin"

DB_NAME="app_db"
DB_USER="app_user"
# Пароль генерируется один раз; при повторном запуске читается из .env чтобы не
# перезаписывать рабочий пароль случайно.
DB_PASS_NEW="$(openssl rand -base64 24 | tr -d '/+=\n')"

SECRET_KEY_NEW="$(openssl rand -base64 48 | tr -d '/+=\n')"

GUNICORN_SOCK="/run/gunicorn.sock"
# Количество воркеров gunicorn:
#   1 CPU  → 2 workers (безопасное значение по умолчанию)
#   2 CPU  → 3 workers, если RAM >= 1 GB (формула: 2*CPU + 1)
#   Менять вручную при необходимости.
WORKERS=2

# =============================================================================
# 1. Обновление системы
# =============================================================================
info "=== 1/10  Обновление пакетов ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    python3 python3-venv python3-pip python3-dev \
    git curl wget unzip \
    nginx \
    postgresql postgresql-contrib \
    redis-server \
    ufw \
    build-essential libpq-dev \
    certbot python3-certbot-nginx

info "Пакеты установлены."

# =============================================================================
# 2. Пользователь deploy
# =============================================================================
info "=== 2/10  Пользователь ${APP_USER} ==="
if ! id "${APP_USER}" &>/dev/null; then
    adduser --disabled-password --gecos "" "${APP_USER}"
    usermod -aG sudo "${APP_USER}"
    info "Пользователь ${APP_USER} создан."
else
    info "Пользователь ${APP_USER} уже существует — пропускаем."
fi

# SSH-ключи root → deploy, чтобы не потерять доступ
if [[ -f /root/.ssh/authorized_keys ]]; then
    mkdir -p /home/${APP_USER}/.ssh
    cp /root/.ssh/authorized_keys /home/${APP_USER}/.ssh/authorized_keys
    chown -R ${APP_USER}:${APP_USER} /home/${APP_USER}/.ssh
    chmod 700 /home/${APP_USER}/.ssh
    chmod 600 /home/${APP_USER}/.ssh/authorized_keys
    info "SSH-ключи скопированы пользователю ${APP_USER}."
fi

# =============================================================================
# 3. Firewall (UFW)
# =============================================================================
info "=== 3/10  Firewall (UFW) ==="
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
info "UFW активирован. Открыты: SSH, HTTP, HTTPS."

# =============================================================================
# 4. PostgreSQL: база и пользователь
# =============================================================================
info "=== 4/10  PostgreSQL ==="
systemctl enable postgresql --now

# Определяем: первый запуск или повторный (берём пароль из существующего .env)
ENV_FILE="${APP_DIR}/current/.env"
if [[ -f "${ENV_FILE}" ]] && grep -q "^DATABASE_URL=" "${ENV_FILE}"; then
    # Извлекаем пароль из существующего DATABASE_URL, не меняем его
    DB_PASS="$(grep "^DATABASE_URL=" "${ENV_FILE}" | sed 's|.*://[^:]*:\([^@]*\)@.*|\1|')"
    info "Используем существующий пароль БД из .env."
else
    DB_PASS="${DB_PASS_NEW}"
    info "Генерируем новый пароль БД."
fi

# Создаём пользователя и базу идемпотентно
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';
  ELSE
    ALTER USER ${DB_USER} WITH PASSWORD '${DB_PASS}';
  END IF;
END
\$\$;

SELECT 'CREATE DATABASE ${DB_NAME}' WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = '${DB_NAME}'
)\gexec

GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
\c ${DB_NAME}
GRANT ALL ON SCHEMA public TO ${DB_USER};
SQL

info "PostgreSQL: база '${DB_NAME}', пользователь '${DB_USER}' готовы."

# =============================================================================
# 5. Redis
# =============================================================================
info "=== 5/10  Redis ==="
systemctl enable redis-server --now
info "Redis запущен."

# =============================================================================
# 6. Директории проекта
# =============================================================================
info "=== 6/10  Директории ==="
mkdir -p "${APP_DIR}/current"
mkdir -p "${APP_DIR}/venv"
mkdir -p "${APP_DIR}/logs"
# media и staticfiles относительно DJANGO_ROOT (manage.py)
# создаются пустыми, но правильные пути выставит deploy.sh
mkdir -p "${APP_DIR}/current/${DJANGO_SUBDIR}/media"
mkdir -p "${APP_DIR}/current/${DJANGO_SUBDIR}/staticfiles"

chown -R ${APP_USER}:${APP_USER} "${APP_DIR}"
chmod 755 "${APP_DIR}"
info "Директории готовы."

# =============================================================================
# 7. Python venv
# =============================================================================
info "=== 7/10  Python venv ==="
if [[ ! -f "${APP_DIR}/venv/bin/activate" ]]; then
    sudo -u ${APP_USER} python3 -m venv "${APP_DIR}/venv"
    info "venv создан."
else
    info "venv уже существует — пропускаем."
fi

# Устанавливаем минимальный набор для gunicorn; остальное — в deploy.sh через requirements.txt
sudo -u ${APP_USER} "${APP_DIR}/venv/bin/pip" install --upgrade pip -q
sudo -u ${APP_USER} "${APP_DIR}/venv/bin/pip" install -q \
    gunicorn \
    psycopg2-binary \
    django \
    pillow \
    dj-database-url \
    whitenoise \
    redis \
    cryptography

info "Python-зависимости (базовые) установлены."

# =============================================================================
# 8. .env — создаём только при первом запуске
# =============================================================================
info "=== 8/10  .env ==="

# SECRET_KEY: при повторном запуске берём из существующего .env
if [[ -f "${ENV_FILE}" ]] && grep -q "^DJANGO_SECRET_KEY=" "${ENV_FILE}"; then
    SECRET_KEY="$(grep "^DJANGO_SECRET_KEY=" "${ENV_FILE}" | cut -d'=' -f2-)"
    info "SECRET_KEY: используем существующий из .env."
else
    SECRET_KEY="${SECRET_KEY_NEW}"
fi

if [[ ! -f "${ENV_FILE}" ]]; then

# ───────────────────────────────────────────────────────────────────
# ВАЖНО: после запуска скрипта отредактируй этот файл:
#   nano /var/www/app/current/.env
# Замени MY_SERVER_IP на реальный IP-адрес или домен сервера.
# ───────────────────────────────────────────────────────────────────
cat > "${ENV_FILE}" <<ENV
# ─── Основные ────────────────────────────────────────────────────────────────
DJANGO_SECRET_KEY=${SECRET_KEY}
DJANGO_DEBUG=0
DJANGO_PRODUCTION=1

# ОБЯЗАТЕЛЬНО: замени MY_SERVER_IP на IP-адрес или домен
DJANGO_ALLOWED_HOSTS=MY_SERVER_IP

# ─── База данных ─────────────────────────────────────────────────────────────
DATABASE_URL=postgres://${DB_USER}:${DB_PASS}@127.0.0.1:5432/${DB_NAME}

# ─── CSRF ────────────────────────────────────────────────────────────────────
# ОБЯЗАТЕЛЬНО: замени MY_SERVER_IP (после SSL — поменяй http на https)
DJANGO_CSRF_TRUSTED_ORIGINS=http://MY_SERVER_IP

# ─── Redis ───────────────────────────────────────────────────────────────────
REDIS_URL=redis://127.0.0.1:6379/0

# ─── SSL (раскомментировать после certbot) ───────────────────────────────────
# DJANGO_SESSION_COOKIE_SECURE=1
# DJANGO_SECURE_SSL_REDIRECT=1
# DJANGO_TRUST_FORWARDED_PROTO=1
ENV

    chown ${APP_USER}:${APP_USER} "${ENV_FILE}"
    chmod 600 "${ENV_FILE}"
    info ".env создан: ${ENV_FILE}"
    warn ">>> Обязательно замени MY_SERVER_IP в ${ENV_FILE} <<<"
else
    info ".env уже существует — не перезаписываем."
fi

# =============================================================================
# 9. Gunicorn: helper-скрипт + systemd unit
#    ВАЖНО: app.service создаём, но НЕ запускаем здесь — только enable.
#    systemctl start app вызывается в deploy.sh после загрузки кода.
# =============================================================================
info "=== 9/10  Gunicorn systemd ==="

# DJANGO_ROOT — абсолютный путь где лежит manage.py и wsgi.py
DJANGO_ROOT="${APP_DIR}/current/${DJANGO_SUBDIR}"

cat > /usr/local/bin/app-start.sh <<STARTSCRIPT
#!/usr/bin/env bash
# Запускает gunicorn, загружая переменные из .env.
# WorkingDirectory должна содержать manage.py проекта.
set -a
source /var/www/app/current/.env 2>/dev/null || true
set +a
exec /var/www/app/venv/bin/gunicorn \\
    nfc_site.wsgi:application \\
    --workers ${WORKERS} \\
    --bind unix:${GUNICORN_SOCK} \\
    --access-logfile /var/www/app/logs/gunicorn-access.log \\
    --error-logfile  /var/www/app/logs/gunicorn-error.log \\
    --log-level info \\
    --timeout 60 \\
    --keep-alive 5 \\
    --max-requests 1000 \\
    --max-requests-jitter 100
STARTSCRIPT

chmod +x /usr/local/bin/app-start.sh

cat > /etc/systemd/system/app.service <<UNIT
[Unit]
Description=nfc_cards gunicorn
After=network.target postgresql.service redis.service
Requires=postgresql.service

[Service]
User=${APP_USER}
Group=${APP_USER}
# WorkingDirectory = папка с manage.py (именно отсюда Python находит nfc_site)
WorkingDirectory=${DJANGO_ROOT}
ExecStart=/usr/local/bin/app-start.sh
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=on-failure
RestartSec=5
# Создаёт /run/gunicorn/ с нужными правами
RuntimeDirectory=gunicorn
RuntimeDirectoryMode=0755
LimitNOFILE=65536
# Не стартует автоматически при загрузке сервера до первого деплоя
# После deploy.sh сервис поднимается и enable работает нормально.

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
# enable — да (стартует после reboot); start — НЕТ (кода ещё нет).
systemctl enable app
info "app.service настроен и включён (НЕ запущен — запустится после deploy.sh)."

# =============================================================================
# 10. Nginx
# =============================================================================
info "=== 10/10  Nginx ==="

# Отключаем дефолтный сайт
rm -f /etc/nginx/sites-enabled/default

cat > /etc/nginx/sites-available/app <<NGINX
# nfc_cards — nginx конфиг
# Домен настраивается позже через certbot

upstream gunicorn_app {
    server unix:${GUNICORN_SOCK} fail_timeout=0;
}

server {
    listen 80;
    server_name _;

    # Лимит загрузки: EDITOR_IMAGE_MAX_BYTES=5MB + запас
    client_max_body_size 20M;

    # ── Security headers ─────────────────────────────────────────────────────
    add_header X-Content-Type-Options  "nosniff"         always;
    add_header X-Frame-Options         "SAMEORIGIN"      always;
    add_header X-XSS-Protection        "1; mode=block"   always;
    add_header Referrer-Policy         "strict-origin-when-cross-origin" always;

    # ── Статика Django (/var/www/app/current/sources/site_admin/staticfiles/) ─
    location /static/ {
        alias ${DJANGO_ROOT}/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # ── Media (загруженные изображения) ──────────────────────────────────────
    location /media/ {
        alias ${DJANGO_ROOT}/media/;
        expires 30d;
        add_header Cache-Control "public";
        access_log off;
    }

    # ── Django / gunicorn ────────────────────────────────────────────────────
    location / {
        # Если gunicorn не запущен — отдаём 502, а не зависаем
        proxy_pass          http://gunicorn_app;
        proxy_set_header    Host              \$host;
        proxy_set_header    X-Real-IP         \$remote_addr;
        proxy_set_header    X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header    X-Forwarded-Proto \$scheme;
        proxy_read_timeout  60;
        proxy_connect_timeout 10;
        proxy_redirect      off;

        # Буфер — отдаём ответ клиенту не дожидаясь полного чтения
        proxy_buffering     on;
        proxy_buffer_size   8k;
        proxy_buffers       8 16k;
    }

    access_log  /var/www/app/logs/nginx-access.log;
    error_log   /var/www/app/logs/nginx-error.log;
}
NGINX

# Nginx работает с сокетом gunicorn — сокет создаётся только после start app.
# Nginx корректно стартует и без активного сокета: вернёт 502 пока gunicorn не поднят.
ln -sf /etc/nginx/sites-available/app /etc/nginx/sites-enabled/app
nginx -t
systemctl enable nginx --now
systemctl reload nginx
info "Nginx настроен."

# =============================================================================
# Итог
# =============================================================================
cat <<SUMMARY

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Сервер подготовлен. Следующие шаги:

  1. Отредактируй .env — замени MY_SERVER_IP:
       nano /var/www/app/current/.env

  2. Загрузи код в /var/www/app/current/ (git или scp).
     Структура должна содержать:
       /var/www/app/current/sources/site_admin/manage.py

  3. Запусти деплой:
       bash /var/www/app/deploy.sh

  После deploy.sh сервис стартует автоматически.

  БД: ${DB_NAME} / пользователь: ${DB_USER}
  Пароль БД: ${ENV_FILE}
  Логи: /var/www/app/logs/
  Лог этой установки: /root/setup-vps.log
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUMMARY
