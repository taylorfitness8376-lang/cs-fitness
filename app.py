from flask import (Flask, redirect, render_template, request,
                   session, url_for, jsonify)
import bcrypt
import os
from datetime import datetime
from database import init_db, get_db, init_app
import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["DATABASE_PATH"] = config.DATABASE_PATH

init_app(app)


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
    return redirect(url_for("cms"))


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
    return render_template("display.html")


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
        "INSERT INTO sessions (name, coach_notes) VALUES (?, ?)",
        (data["name"], data.get("coach_notes", ""))
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
    db.execute("UPDATE sessions SET name=?, coach_notes=? WHERE id=?",
               (data["name"], data.get("coach_notes", ""), sid))
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


# ── Schedule logic ────────────────────────────────────────


def get_current_session():
    db = get_db()

    # 1. Check override
    ov = db.execute("SELECT session_id FROM override WHERE id=1").fetchone()
    if ov and ov["session_id"]:
        return _session_to_dict(ov["session_id"], db)

    # 2. Walk back through days (up to 7) to find last scheduled slot
    now = datetime.now()
    current_day = now.weekday()      # 0=Mon … 6=Sun
    current_time = now.strftime("%H:%M")

    for days_back in range(7):
        check_day = (current_day - days_back) % 7
        check_time = current_time if days_back == 0 else "23:59"
        row = db.execute(
            "SELECT session_id FROM schedule "
            "WHERE day_of_week=? AND start_time<=? "
            "ORDER BY start_time DESC LIMIT 1",
            (check_day, check_time)
        ).fetchone()
        if row:
            return _session_to_dict(row["session_id"], db)

    return None


# ── Public session endpoint (polled by TV) ────────────────

@app.route("/api/session")
def api_current_session():
    result = get_current_session()
    if result is None:
        return jsonify({"name": None}), 200
    return jsonify(result)


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
        "UPDATE override SET session_id=?, set_at=CURRENT_TIMESTAMP WHERE id=1",
        (sid,)
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
