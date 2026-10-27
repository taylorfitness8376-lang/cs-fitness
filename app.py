from flask import (Flask, redirect, render_template, request,
                   session, url_for, jsonify)
import bcrypt
import os
import sys
from datetime import datetime
from jinja2 import ChoiceLoader, FileSystemLoader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
for _sub in ("8-week-app", "tv"):
    _sub_path = os.path.join(BASE_DIR, _sub)
    if _sub_path not in sys.path:
        sys.path.append(_sub_path)

from database import init_db, get_db, init_app
from challenge import challenge_bp
from challenge_progress import challenge_progress_bp
from challenge_blocks import challenge_blocks_bp
import config

app = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, "8-week-app", "static"),
    static_url_path="/static",
)
app.jinja_loader = ChoiceLoader([
    FileSystemLoader(os.path.join(BASE_DIR, "landing")),
    FileSystemLoader(os.path.join(BASE_DIR, "8-week-app", "templates")),
    FileSystemLoader(os.path.join(BASE_DIR, "tv", "templates")),
])
app.secret_key = config.SECRET_KEY
app.config["DATABASE_PATH"] = config.DATABASE_PATH

init_app(app)
app.register_blueprint(challenge_bp)
app.register_blueprint(challenge_progress_bp)
app.register_blueprint(challenge_blocks_bp)

with app.app_context():
    try:
        init_db()
    except Exception:
        pass


def require_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authed"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/tv")
def tv_subpage():
    return redirect(url_for("cms"))


@app.route("/8-week-app")
def challenge_subpage():
    return redirect("/challenge")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        pw = request.form.get("password", "").encode()
        if bcrypt.checkpw(pw, config.PASSWORD_HASH):
            session["authed"] = True
            return redirect(url_for("cms"))
        error = "Incorrect password"
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/cms")
@require_auth
def cms():
    return render_template("cms.html")


@app.route("/display")
def display():
    initial_session = get_current_session() or {"name": None}
    resp = app.make_response(render_template("display.html", initial_session=initial_session))
    resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp


@app.route("/sw-display.js")
def sw_display():
    sw_code = """const CACHE_NAME = 'cs-fitness-tv-v2';
const SHELL_URLS = ['/display', '/static/logo.jpg'];

self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL_URLS).catch(() => {}))
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.pathname === '/display') {
    event.respondWith(
      fetch(event.request)
        .then(resp => {
          if (resp && resp.ok) {
            const copy = resp.clone();
            caches.open(CACHE_NAME).then(c => c.put('/display', copy));
            return resp;
          }
          return caches.match('/display').then(cached => cached || resp);
        })
        .catch(() => caches.match('/display'))
    );
  } else if (url.pathname === '/static/logo.jpg') {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request))
    );
  }
});
"""
    resp = app.make_response(sw_code)
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Cache-Control"] = "no-cache"
    return resp



# ── Sessions API ──────────────────────────────────────────

def _session_to_dict(session_id, db):
    row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if row is None:
        return None
    blocks = db.execute(
        "SELECT * FROM blocks WHERE session_id=? ORDER BY sort_order, id", (session_id,)
    ).fetchall()
    result = dict(row)
    result["blocks"] = []
    for b in blocks:
        exercises = db.execute(
            "SELECT * FROM exercises WHERE block_id=? ORDER BY sort_order, id", (b["id"],)
        ).fetchall()
        block = dict(b)
        block["exercises"] = [dict(e) for e in exercises]
        result["blocks"].append(block)
    return result


def _save_blocks(session_id, blocks, db):
    for i, block in enumerate(blocks):
        cur = db.execute(
            "INSERT INTO blocks (session_id, label, focus, sort_order) VALUES (?,?,?,?)",
            (session_id, block["label"], block.get("focus", ""), i)
        )
        block_id = cur.lastrowid
        for j, ex in enumerate(block.get("exercises", [])):
            db.execute(
                "INSERT INTO exercises (block_id, code, name, sets_reps, sort_order) "
                "VALUES (?,?,?,?,?)",
                (block_id, ex.get("code", ""), ex["name"], ex.get("sets_reps", ""), j)
            )


@app.route("/api/sessions", methods=["GET"])
@require_auth
def list_sessions():
    db = get_db()
    rows = db.execute("SELECT * FROM sessions ORDER BY name").fetchall()
    sessions = []
    for row in rows:
        s = dict(row)
        counts = db.execute(
            "SELECT COUNT(*) as bc, "
            "(SELECT COUNT(*) FROM exercises e JOIN blocks b ON e.block_id=b.id "
            " WHERE b.session_id=?) as ec FROM blocks WHERE session_id=?",
            (row["id"], row["id"])
        ).fetchone()
        s["block_count"] = counts["bc"]
        s["exercise_count"] = counts["ec"]
        sessions.append(s)
    return jsonify(sessions)


@app.route("/api/sessions", methods=["POST"])
@require_auth
def create_session():
    data = request.get_json()
    db = get_db()
    cur = db.execute(
        "INSERT INTO sessions (name, coach_notes, session_type) VALUES (?, ?, ?)",
        (data["name"], data.get("coach_notes", ""), data.get("session_type", "strength"))
    )
    session_id = cur.lastrowid
    _save_blocks(session_id, data.get("blocks", []), db)
    db.commit()
    return jsonify(_session_to_dict(session_id, db)), 201


@app.route("/api/sessions/<int:sid>", methods=["GET"])
@require_auth
def get_session(sid):
    db = get_db()
    result = _session_to_dict(sid, db)
    if result is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(result)


@app.route("/api/sessions/<int:sid>", methods=["PUT"])
@require_auth
def update_session(sid):
    data = request.get_json()
    db = get_db()
    db.execute("UPDATE sessions SET name=?, coach_notes=?, session_type=? WHERE id=?",
               (data["name"], data.get("coach_notes", ""), data.get("session_type", "strength"), sid))
    db.execute("DELETE FROM blocks WHERE session_id=?", (sid,))
    _save_blocks(sid, data.get("blocks", []), db)
    db.commit()
    return jsonify(_session_to_dict(sid, db))


@app.route("/api/sessions/<int:sid>", methods=["DELETE"])
@require_auth
def delete_session(sid):
    db = get_db()
    db.execute("DELETE FROM sessions WHERE id=?", (sid,))
    db.commit()
    return "", 204


@app.route("/api/sessions/export", methods=["GET"])
@require_auth
def export_sessions():
    db = get_db()
    rows = db.execute("SELECT id FROM sessions ORDER BY name").fetchall()
    return jsonify([_session_to_dict(row["id"], db) for row in rows])


@app.route("/api/sessions/import", methods=["POST"])
@require_auth
def import_sessions():
    data = request.get_json()
    if not isinstance(data, list):
        return jsonify({"error": "expected a list"}), 400
    db = get_db()
    existing_names = {r["name"] for r in db.execute("SELECT name FROM sessions").fetchall()}
    added = 0
    for s in data:
        if s.get("name") and s["name"] not in existing_names:
            cur = db.execute(
                "INSERT INTO sessions (name, coach_notes, session_type) VALUES (?,?,?)",
                (s["name"], s.get("coach_notes", ""), s.get("session_type", "strength"))
            )
            _save_blocks(cur.lastrowid, s.get("blocks", []), db)
            existing_names.add(s["name"])
            added += 1
    db.commit()
    return jsonify({"added": added, "skipped": len(data) - added})


# ── Schedule logic ────────────────────────────────────────


def get_current_session():
    db = get_db()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    # 1. Manual override takes precedence, but only for the day it was published
    ov = db.execute("SELECT session_id, set_at FROM override WHERE id=1").fetchone()
    if ov and ov["session_id"] and (not ov["set_at"] or str(ov["set_at"])[:10] == today):
        return _session_to_dict(ov["session_id"], db)

    # 2. Today's calendar entry
    row = db.execute("SELECT session_id FROM calendar WHERE date=?", (today,)).fetchone()
    if row and row["session_id"]:
        return _session_to_dict(row["session_id"], db)

    # 3. Walk back through weekly schedule (up to 7 days) to find active slot
    current_day = now.weekday()      # 0=Mon … 6=Sun
    current_time = now.strftime("%H:%M")

    for days_back in range(7):
        check_day = (current_day - days_back) % 7
        check_time = current_time if days_back == 0 else "23:59"
        sched_row = db.execute(
            "SELECT session_id FROM schedule "
            "WHERE day_of_week=? AND start_time<=? "
            "ORDER BY start_time DESC LIMIT 1",
            (check_day, check_time)
        ).fetchone()
        if sched_row and sched_row["session_id"]:
            return _session_to_dict(sched_row["session_id"], db)

    return None


# ── Calendar CRUD ─────────────────────────────────────────

@app.route("/api/calendar", methods=["GET"])
@require_auth
def get_calendar():
    start = request.args.get("start", "")
    end   = request.args.get("end", "")
    db = get_db()
    rows = db.execute(
        "SELECT date, session_id FROM calendar WHERE date >= ? AND date <= ? ORDER BY date",
        (start, end)
    ).fetchall()
    result = []
    for row in rows:
        s = _session_to_dict(row["session_id"], db)
        if s:
            s["date"] = row["date"]
            result.append(s)
    return jsonify(result)


@app.route("/api/calendar", methods=["POST"])
@require_auth
def set_calendar():
    data = request.get_json()
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO calendar (date, session_id) VALUES (?, ?)",
        (data["date"], data["session_id"])
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/calendar/<date>", methods=["DELETE"])
@require_auth
def delete_calendar(date):
    db = get_db()
    db.execute("DELETE FROM calendar WHERE date=?", (date,))
    db.commit()
    return "", 204


# ── Public session endpoint (polled by TV) ────────────────

@app.route("/api/session")
def api_current_session():
    result = get_current_session()
    payload = {"name": None} if result is None else result
    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp, 200


# ── Schedule CRUD ─────────────────────────────────────────

@app.route("/api/schedule", methods=["GET"])
@require_auth
def get_schedule():
    db = get_db()
    rows = db.execute(
        "SELECT sc.*, s.name as session_name "
        "FROM schedule sc JOIN sessions s ON s.id=sc.session_id "
        "ORDER BY sc.day_of_week, sc.start_time"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/schedule", methods=["POST"])
@require_auth
def save_schedule():
    """Replace entire schedule with submitted slots."""
    slots = request.get_json()  # [{day_of_week, start_time, session_id}, ...]
    db = get_db()
    db.execute("DELETE FROM schedule")
    for slot in slots:
        db.execute(
            "INSERT INTO schedule (day_of_week, start_time, session_id) VALUES (?,?,?)",
            (slot["day_of_week"], slot["start_time"], slot["session_id"])
        )
    db.commit()
    return jsonify({"ok": True})


# ── Override ──────────────────────────────────────────────

@app.route("/api/publish", methods=["POST"])
@require_auth
def publish():
    sid = request.get_json().get("session_id")
    db = get_db()
    db.execute(
        "UPDATE override SET session_id=?, set_at=? WHERE id=1",
        (sid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/publish/clear", methods=["POST"])
@require_auth
def clear_override():
    db = get_db()
    db.execute("UPDATE override SET session_id=NULL, set_at=NULL WHERE id=1")
    db.commit()
    return jsonify({"ok": True})


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)
