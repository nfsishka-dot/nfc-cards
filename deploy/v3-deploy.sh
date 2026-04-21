#!/usr/bin/env bash
# Production Hardening v3 — GitHub Actions → VPS.
# Запуск на сервере: bash -s < deploy/v3-deploy.sh
# .env не перезаписывается (только source).
#
# Опционально в окружении или в .env на сервере:
#   HEALTHCHECK_BASE=http://127.0.0.1
#   DEPLOY_HEALTHCHECK_PUBLIC_URL=   # третья проверка; пусто = ещё раз /
#   ALLOW_DB_RISK_ROLLBACK=false     # true — разрешить git rollback после migrate
#
set -euo pipefail

APP_DIR="/var/www/nfc-cards"
DJANGO_DIR="$APP_DIR/sources/site_admin"
VENV="$APP_DIR/venv"
ENV_FILE="$APP_DIR/.env"
LOCK_FILE="/var/lock/nfc-deploy.lock"
ALLOW_DB_RISK_ROLLBACK="${ALLOW_DB_RISK_ROLLBACK:-false}"

FINAL_STATUS="DEPLOY STATUS: FAILED"
USE_FLOCK=""

log() { echo "[v3-deploy] $*"; }

sc() {
  if [[ "$(id -u)" -eq 0 ]]; then
    systemctl "$@"
  else
    sudo -n systemctl "$@"
  fi
}

load_env() {
  set -a
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  set +a
  HEALTHCHECK_BASE="${HEALTHCHECK_BASE:-http://127.0.0.1}"
}

migration_count() {
  cd "$DJANGO_DIR"
  local c
  c="$("$VENV/bin/python" manage.py shell -c "
from django.db.migrations.recorder import MigrationRecorder
print(MigrationRecorder.Migration.objects.count())
" 2>/dev/null | tail -1 | tr -d '[:space:]')"
  echo "${c:-0}"
}

preflight_django() {
  cd "$DJANGO_DIR"
  log "preflight: manage.py check"
  "$VENV/bin/python" manage.py check --fail-level ERROR

  log "preflight: migrate --plan (read-only)"
  if ! "$VENV/bin/python" manage.py migrate --plan --noinput; then
    log "ERROR: migrate --plan failed"
    return 1
  fi

  log "preflight: showmigrations (tail)"
  "$VENV/bin/python" manage.py showmigrations 2>/dev/null | tail -40 || true
}

run_pip() {
  log "pip install"
  "$VENV/bin/pip" install --upgrade pip -q
  "$VENV/bin/pip" install -r "$DJANGO_DIR/requirements.txt" -q
}

apply_migrate() {
  cd "$DJANGO_DIR"
  log "migrate --noinput"
  "$VENV/bin/python" manage.py migrate --noinput

  log "verify: migrate --check (no pending migrations)"
  if ! "$VENV/bin/python" manage.py migrate --check; then
    log "ERROR: migrate --check failed after migrate"
    return 1
  fi
}

collect_static_clear() {
  cd "$DJANGO_DIR"
  log "collectstatic --noinput --clear"
  "$VENV/bin/python" manage.py collectstatic --noinput --clear -v 0
}

fix_media_perms() {
  mkdir -p "$DJANGO_DIR/media" "$APP_DIR/logs"
  local u="${SUDO_USER:-deploy}"
  if id "$u" &>/dev/null; then
    chown -R "$u:$u" "$DJANGO_DIR/media" "$APP_DIR/logs" 2>/dev/null || true
  fi
}

healthcheck_all() {
  local base="${HEALTHCHECK_BASE:-http://127.0.0.1}"
  base="${base%/}"
  local third="${DEPLOY_HEALTHCHECK_PUBLIC_URL:-}"
  local code

  for url in "${base}/" "${base}/admin/"; do
    code="$(curl -sS -L -o /dev/null -w "%{http_code}" --connect-timeout 8 "$url" || echo "000")"
    log "healthcheck: $url -> HTTP $code"
    case "$code" in
      200|301|302) ;;
      *) log "healthcheck FAILED: $url"; return 1 ;;
    esac
  done

  if [[ -n "$third" ]]; then
    code="$(curl -sS -L -o /dev/null -w "%{http_code}" --connect-timeout 8 "$third" || echo "000")"
    log "healthcheck (public URL): $third -> HTTP $code"
    case "$code" in
      200|301|302) ;;
      *) log "healthcheck FAILED: $third"; return 1 ;;
    esac
  else
    log "healthcheck (public): fallback ${base}/"
    code="$(curl -sS -L -o /dev/null -w "%{http_code}" --connect-timeout 8 "${base}/" || echo "000")"
    log "healthcheck: ${base}/ -> HTTP $code"
    case "$code" in
      200|301|302) ;;
      *) return 1 ;;
    esac
  fi
  return 0
}

rollback_git_safe() {
  local prev="$1"
  local mig_applied="$2"

  if [[ "$mig_applied" == "1" && "$ALLOW_DB_RISK_ROLLBACK" != "true" ]]; then
    log "ROLLBACK SKIPPED: migrations applied; set ALLOW_DB_RISK_ROLLBACK=true to force git rollback"
    log "WARNING: DB may not match rolled-back code — manual intervention may be required"
    FINAL_STATUS="DEPLOY STATUS: FAILED"
    return 1
  fi

  log "ROLLBACK: git reset --hard $prev"
  cd "$APP_DIR"
  git reset --hard "$prev"
  load_env
  run_pip
  cd "$DJANGO_DIR"
  log "rollback: migrate --noinput (reconcile code vs DB)"
  "$VENV/bin/python" manage.py migrate --noinput || true
  collect_static_clear || true
  fix_media_perms
  sc restart app
  sc restart nginx
  sleep 4
  if healthcheck_all; then
    FINAL_STATUS="DEPLOY STATUS: ROLLBACK EXECUTED"
    return 0
  fi
  return 1
}

release_lock() {
  if [[ "$USE_FLOCK" == "1" ]]; then
    flock -u 200 2>/dev/null || true
  fi
  rmdir "${LOCK_FILE}.dir" 2>/dev/null || true
}

acquire_lock() {
  mkdir -p /var/lock
  if command -v flock >/dev/null 2>&1; then
    exec 200>"$LOCK_FILE"
    if ! flock -n 200; then
      log "another deploy holds $LOCK_FILE"
      echo "DEPLOY STATUS: FAILED"
      exit 1
    fi
    USE_FLOCK="1"
    log "lock acquired (flock): $LOCK_FILE"
  else
    if ! mkdir "${LOCK_FILE}.dir" 2>/dev/null; then
      log "lock busy: ${LOCK_FILE}.dir"
      echo "DEPLOY STATUS: FAILED"
      exit 1
    fi
    log "lock acquired (mkdir): ${LOCK_FILE}.dir"
  fi
}

trap 'release_lock' EXIT

# -----------------------------------------------------------------------------
acquire_lock

if [[ ! -f "$ENV_FILE" ]]; then
  log "ERROR: missing $ENV_FILE"
  echo "DEPLOY STATUS: FAILED"
  exit 1
fi

if [[ ! -d "$APP_DIR/.git" ]]; then
  log "ERROR: not a git repo: $APP_DIR"
  echo "DEPLOY STATUS: FAILED"
  exit 1
fi

cd "$APP_DIR"

BACKUP_DIR="/root/deploy-backups/$(date +%s)"
mkdir -p "$BACKUP_DIR"
log "STEP: rsync snapshot → $BACKUP_DIR"
rsync -a "$DJANGO_DIR/" "$BACKUP_DIR/django-snapshot/" || true

PREV_COMMIT="$(git rev-parse HEAD)"
log "previous HEAD: $PREV_COMMIT"

log "STEP: git fetch + reset origin/main"
git fetch origin
git stash push -m "gha-v3-$(date +%s)" --quiet || true
git reset --hard origin/main
log "new HEAD: $(git rev-parse HEAD)"

load_env
run_pip

MIG_BEFORE="$(migration_count)"
log "migration recorder count (before migrate): $MIG_BEFORE"

if ! preflight_django; then
  log "preflight FAILED — revert git"
  git reset --hard "$PREV_COMMIT"
  echo "DEPLOY STATUS: FAILED"
  exit 1
fi

if ! apply_migrate; then
  log "migrate failed — revert git"
  git reset --hard "$PREV_COMMIT"
  echo "DEPLOY STATUS: FAILED"
  exit 1
fi

MIG_AFTER="$(migration_count)"
log "migration recorder count (after migrate): $MIG_AFTER"

MIGRATIONS_APPLIED="0"
if [[ "$MIG_AFTER" =~ ^[0-9]+$ && "$MIG_BEFORE" =~ ^[0-9]+$ ]] && (( MIG_AFTER > MIG_BEFORE )); then
  MIGRATIONS_APPLIED="1"
  log "note: migration recorder count increased (new migrations applied)"
fi

if ! collect_static_clear; then
  log "collectstatic failed"
  if rollback_git_safe "$PREV_COMMIT" "$MIGRATIONS_APPLIED"; then
    echo "$FINAL_STATUS"
    exit 1
  fi
  echo "DEPLOY STATUS: FAILED"
  exit 1
fi

fix_media_perms

log "STEP: restart app + nginx"
sc restart app
sc restart nginx
sleep 4

if healthcheck_all; then
  FINAL_STATUS="DEPLOY STATUS: SUCCESS"
  log "gunicorn processes:"
  ps auxww | grep -E '[g]unicorn' || true
  echo "$FINAL_STATUS"
  exit 0
fi

log "healthcheck FAILED — attempting rollback"
if rollback_git_safe "$PREV_COMMIT" "$MIGRATIONS_APPLIED"; then
  echo "$FINAL_STATUS"
  exit 1
fi

echo "$FINAL_STATUS"
exit 2
