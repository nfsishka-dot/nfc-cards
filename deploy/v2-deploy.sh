#!/usr/bin/env bash
# Production deploy v2: git sync → Django → restart → healthcheck → rollback (git) при FAIL.
# Запуск на VPS из GitHub Actions: bash -s < deploy/v2-deploy.sh
# Не изменяет содержимое .env — только source.
#
# Откат: git reset --hard к коммиту до деплоя + pip + migrate + collectstatic + restart.
# Если на «плохом» деплое применились новые миграции, после отката БД может не совпадать
# с кодом — тогда нужен ручной разбор (редкий случай).
set -euo pipefail

APP_DIR="/var/www/nfc-cards"
DJANGO_DIR="$APP_DIR/sources/site_admin"
VENV="$APP_DIR/venv"
ENV_FILE="$APP_DIR/.env"
HEALTHCHECK_URL="${HEALTHCHECK_URL:-http://127.0.0.1/}"

echo "PRODUCTION DEPLOY v2 START"

sc() {
  if [[ "$(id -u)" -eq 0 ]]; then
    systemctl "$@"
  else
    sudo -n systemctl "$@"
  fi
}

run_django_pipeline() {
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a

  echo "pip install"
  "$VENV/bin/pip" install --upgrade pip -q
  "$VENV/bin/pip" install -r "$DJANGO_DIR/requirements.txt" -q

  cd "$DJANGO_DIR"
  echo "migrate"
  "$VENV/bin/python" manage.py migrate --noinput
  echo "collectstatic"
  "$VENV/bin/python" manage.py collectstatic --noinput

  mkdir -p "$DJANGO_DIR/media" "$APP_DIR/logs"
  DEPLOY_USER="${SUDO_USER:-deploy}"
  if id "$DEPLOY_USER" &>/dev/null; then
    chown -R "$DEPLOY_USER:$DEPLOY_USER" "$DJANGO_DIR/media" "$APP_DIR/logs" 2>/dev/null || true
  fi
}

health_ok() {
  local code
  code="$(curl -sS -L -o /dev/null -w "%{http_code}" --connect-timeout 5 "$HEALTHCHECK_URL" || echo "000")"
  case "$code" in
    200|301|302) return 0 ;;
    *) echo "healthcheck HTTP $code (expected 200 or redirect)"; return 1 ;;
  esac
}

rollback_git() {
  local prev="$1"
  echo "ROLLBACK: git reset --hard $prev"
  cd "$APP_DIR"
  git reset --hard "$prev"
  run_django_pipeline
  sc restart app
  sc restart nginx
  sleep 2
}

# -----------------------------------------------------------------------------
cd "$APP_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: missing $ENV_FILE"
  exit 1
fi

if [[ ! -d "$APP_DIR/.git" ]]; then
  echo "ERROR: not a git repo: $APP_DIR"
  exit 1
fi

BACKUP_DIR="/root/deploy-backups/$(date +%s)"
mkdir -p "$BACKUP_DIR"
echo "optional file snapshot: rsync django → $BACKUP_DIR"
rsync -a "$DJANGO_DIR/" "$BACKUP_DIR/django-snapshot/" || true

PREV_COMMIT="$(git rev-parse HEAD)"
echo "previous HEAD: $PREV_COMMIT"

echo "git sync"
git fetch origin
git stash push -m "gha-v2-auto-$(date +%s)" --quiet || true
git reset --hard origin/main
NEW_COMMIT="$(git rev-parse HEAD)"
echo "new HEAD: $NEW_COMMIT"

run_django_pipeline

echo "restart services"
sc restart app
sc restart nginx
sleep 3

echo "healthcheck: $HEALTHCHECK_URL"
if health_ok; then
  echo "DEPLOY SUCCESS (HTTP OK)"
  ps auxww | grep -E '[g]unicorn' || true
  echo "PRODUCTION DEPLOY v2 DONE"
  exit 0
fi

echo "DEPLOY FAILED — rolling back to $PREV_COMMIT"
rollback_git "$PREV_COMMIT" || true

echo "post-rollback healthcheck"
if health_ok; then
  echo "ROLLBACK STABLE — site responds after revert"
  exit 1
fi

echo "CRITICAL: rollback did not restore health — manual intervention needed"
exit 2
