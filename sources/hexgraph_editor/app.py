from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.exceptions import RequestEntityTooLarge
from FlashSQL import Client
import uuid
from datetime import datetime
import os
import json
import socket
import time
from pathlib import Path

port = int(os.getenv("PORT", 1020))
# 0.0.0.0 — доступ с других устройств в локальной сети (телефон по Wi‑Fi). Только с ПК: FLASK_HOST=127.0.0.1
host = os.getenv("FLASK_HOST", "0.0.0.0")


def _guess_lan_url(listen_port: int) -> str | None:
    """IP для доступа с телефона в той же сети, что и этот ПК (не 127.0.0.1)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.25)
        s.connect(("192.168.0.1", 1))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return f"http://{ip}:{listen_port}/"
    except OSError:
        pass
    return None
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-production")

_db_path = os.getenv("HEXGRAPH_DB", "database.db")
_last_db_err = None
db = None
for _attempt in range(80):
    try:
        db = Client(_db_path)
        break
    except Exception as e:
        _last_db_err = e
        ename = type(e).__name__
        msg = str(e).lower()
        if ename == "BusyError" or "locked" in msg:
            time.sleep(0.05)
            continue
        raise
if db is None:
    raise RuntimeError(
        "Не удалось открыть базу данных (%s): файл занят другим процессом. "
        "Закройте второй экземпляр python app.py, окно DB Browser с этой БД и другие программы, "
        "которые держат database.db открытой, затем запустите сервер снова."
        % _db_path
    ) from _last_db_err

# Черновики предпросмотра (большой HTML не помещается в cookie-сессию)
_preview_store = {}

_max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "25"))
app.config["MAX_CONTENT_LENGTH"] = _max_upload_mb * 1024 * 1024
# Quill content is sent as regular form fields; Werkzeug limits in-memory form size.
app.config["MAX_FORM_MEMORY_SIZE"] = _max_upload_mb * 1024 * 1024

@app.errorhandler(RequestEntityTooLarge)
def handle_request_too_large(_err):
    return (
        f"Request Entity Too Large: пост слишком большой. "
        f"Лимит сейчас: {_max_upload_mb} MB.",
        413,
    )

@app.route('/favicon.ico')
def favicon():
    return '', 204

def _parse_background(background_raw):
    if not background_raw:
        return None
    try:
        return json.loads(background_raw)
    except Exception:
        return None


@app.route('/')
def index():
    static_dir = Path(app.static_folder)
    backgrounds_dir = static_dir / "backgrounds"
    allowed_ext = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
    background_images = []
    if backgrounds_dir.exists():
        for p in backgrounds_dir.iterdir():
            if p.is_file() and p.suffix.lower() in allowed_ext:
                background_images.append(p.name)
    background_images.sort()
    restore_key = request.args.get("restore")
    editor_restore = None
    if restore_key and restore_key in _preview_store:
        editor_restore = _preview_store.pop(restore_key)
    return render_template(
        "index.html",
        background_images=background_images,
        editor_restore=editor_restore,
    )


@app.route("/preview", methods=["POST"])
def preview_post():
    content = request.form.get("content") or ""
    title = request.form.get("title") or ""
    background_raw = request.form.get("background_value")
    background = _parse_background(background_raw)
    pid = str(uuid.uuid4())
    _preview_store[pid] = {
        "content": content,
        "title": title,
        "background": background,
        "background_value": background_raw or '{"type":"color","value":"#ffffff"}',
    }
    session["preview_id"] = pid
    return redirect(url_for("preview_get"))


@app.route("/preview", methods=["GET"])
def preview_get():
    pid = session.get("preview_id")
    if not pid or pid not in _preview_store:
        return redirect(url_for("index"))
    data = _preview_store[pid]
    return render_template(
        "preview_post.html",
        title=data.get("title") or "Предпросмотр",
        content=data["content"],
        background=data.get("background"),
    )


@app.route("/finalize_post", methods=["POST"])
def finalize_post():
    pid = session.get("preview_id")
    if not pid or pid not in _preview_store:
        session.pop("preview_id", None)
        return redirect(url_for("index"))
    data = _preview_store.pop(pid)
    session.pop("preview_id", None)
    post_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.set(
        post_id,
        {
            "title": data.get("title") or "",
            "content": data["content"],
            "timestamp": timestamp,
            "background": data.get("background"),
        },
    )
    return redirect(url_for("view_post", post_id=post_id))


@app.route("/restore_editor")
def restore_editor():
    pid = session.get("preview_id")
    session.pop("preview_id", None)
    if not pid or pid not in _preview_store:
        return redirect(url_for("index"))
    data = _preview_store.pop(pid)
    rid = str(uuid.uuid4())
    _preview_store[rid] = data
    return redirect(url_for("index", restore=rid))

@app.route('/create_post', methods=['POST'])
def create_post():
    """Прямое сохранение без предпросмотра (совместимость). Основной сценарий — finalize_post."""
    title = request.form.get('title') or ''
    content = request.form.get('content')
    background = _parse_background(request.form.get('background_value'))

    post_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.set(post_id, {'title': title, 'content': content, 'timestamp': timestamp, 'background': background})

    return redirect(url_for('view_post', post_id=post_id))

@app.route('/post/<post_id>')
def view_post(post_id):
    post = db.get(post_id)
    if not post:
        return ("Post not found", 404)
    post["views"] = post.get("views", 0) + 1
    db.set(post_id, post)
    return render_template(
        'post.html',
        title=post['title'],
        content=post['content'],
        timestamp=post['timestamp'],
        views=post['views'],
        background=post.get('background')
    )

if __name__ == "__main__":
    if host == "0.0.0.0":
        lan = _guess_lan_url(port)
        print()
        print("  Локальная сеть: сервер слушает 0.0.0.0 — можно зайти с телефона в той же Wi‑Fi.")
        if lan:
            print(f"  Откройте в браузере телефона: {lan}")
        else:
            print(f"  Адрес: http://<IP_этого_ПК>:{port}/  (узнайте IP: ipconfig → IPv4 основного адаптера)")
        print(f"  Если страница не грузится — разрешите входящие подключения для Python на порту {port} (брандмауэр Windows).")
        print()
    app.run(host=host, port=port, debug=True, use_reloader=False)
