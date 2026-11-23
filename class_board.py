import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from database import get_db


classes_bp = Blueprint("classes", __name__, url_prefix="/classes",
                       template_folder="tv/templates")
GYM_TIMEZONE = ZoneInfo("Europe/London")


def now_local():
    return datetime.now(GYM_TIMEZONE)


def ensure_tables(db):
    db.execute("""CREATE TABLE IF NOT EXISTS class_workouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS class_board_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        workout_id INTEGER REFERENCES class_workouts(id),
        expires_at TEXT,
        seeded INTEGER NOT NULL DEFAULT 0,
        templates_seeded INTEGER NOT NULL DEFAULT 0,
        published_content TEXT
    )""")
    columns = {row["name"] for row in db.execute("PRAGMA table_info(class_board_state)")}
    if "templates_seeded" not in columns:
        db.execute("ALTER TABLE class_board_state ADD COLUMN templates_seeded INTEGER NOT NULL DEFAULT 0")
    if "published_content" not in columns:
        db.execute("ALTER TABLE class_board_state ADD COLUMN published_content TEXT")
        db.execute(
            """UPDATE class_board_state SET published_content=(
               SELECT content FROM class_workouts WHERE id=class_board_state.workout_id)"""
        )
    db.execute("INSERT OR IGNORE INTO class_board_state(id) VALUES(1)")
    state = db.execute("SELECT * FROM class_board_state WHERE id=1").fetchone()
    if not state["templates_seeded"]:
        samples = json.loads(
            (Path(__file__).parent / "data" / "class_workouts.json").read_text()
        )
        existing_types = {json.loads(row["content"])["class_type"] for row in
                          db.execute("SELECT content FROM class_workouts")}
        for sample in samples:
            if not state["seeded"] or sample["class_type"] not in existing_types:
                db.execute("INSERT INTO class_workouts(content) VALUES(?)", (json.dumps(sample),))
        db.execute("UPDATE class_board_state SET seeded=1, templates_seeded=1 WHERE id=1")
    db.commit()


@classes_bp.before_request
def protect_planner():
    public = request.endpoint in ("classes.display", "classes.board")
    if not public:
        if not session.get("authed"):
            if request.path.startswith("/classes/api/"):
                return jsonify(error="Coach sign-in required."), 401
            return redirect(url_for("login", next="/classes"))
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            expected = session.get("class_csrf", "")
            supplied = request.headers.get("X-CSRF-Token", "")
            if not expected or not hmac.compare_digest(expected.encode(), supplied.encode()):
                return jsonify(
                    error="Your session changed. Your edits are still here; try saving again.",
                    code="csrf_expired",
                ), 403
        if request.endpoint in ("classes.planner", "classes.planner_data"):
            # Set the token before the page starts parallel preview/image requests.
            session.setdefault("class_csrf", secrets.token_hex(32))
    ensure_tables(get_db())


@classes_bp.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def read_workout(db, wid):
    row = db.execute("SELECT id, content FROM class_workouts WHERE id=?", (wid,)).fetchone()
    return {"id": row["id"], **json.loads(row["content"])} if row else None


def validate_workout(data, allow_draft=False):
    if not isinstance(data, dict):
        raise ValueError("Provide a workout object.")
    cleaned = {}
    for key, limit in (("title", 120), ("class_type", 60), ("notes", 1000)):
        value = data.get(key, "")
        if not isinstance(value, str) or len(value.strip()) > limit:
            raise ValueError(f"{key.replace('_', ' ').title()} must be text up to {limit} characters.")
        cleaned[key] = value.strip()
    if not cleaned["title"]:
        raise ValueError("Give the workout a title.")
    sections = data.get("sections")
    if not isinstance(sections, list) or not 1 <= len(sections) <= 20:
        raise ValueError("Add between 1 and 20 workout sections.")
    cleaned["sections"] = []
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError("Each section needs a heading and workout text.")
        heading, body = section.get("title"), section.get("body")
        if not isinstance(heading, str) or not heading.strip() or len(heading) > 100:
            raise ValueError("Each section needs a heading up to 100 characters.")
        if not isinstance(body, str) or (not allow_draft and not body.strip()) or len(body) > 6000:
            raise ValueError("Each section needs workout text up to 6000 characters.")
        cleaned["sections"].append({"title": heading.strip(), "body": body.strip()})
    return cleaned


@classes_bp.route("")
def planner():
    return render_template("class_planner.html")


@classes_bp.route("/display")
def display():
    return render_template("class_display.html")


@classes_bp.route("/api/planner")
def planner_data():
    db = get_db()
    return jsonify(
        csrf_token=session["class_csrf"],
        workouts=[read_workout(db, row["id"]) for row in
                  db.execute("SELECT id FROM class_workouts ORDER BY id DESC").fetchall()],
        board=current_board(db),
    )


@classes_bp.route("/api/preview/<int:wid>")
def preview(wid):
    item = read_workout(get_db(), wid)
    if item is None:
        return jsonify(error="Workout not found."), 404
    return jsonify(workout=item, mode="preview", until=None, slot=None)


@classes_bp.route("/api/workouts", methods=["POST"])
@classes_bp.route("/api/workouts/<int:wid>", methods=["PUT"])
def save_workout(wid=None):
    db = get_db()
    if wid is not None and read_workout(db, wid) is None:
        return jsonify(error="Workout not found."), 404
    try:
        data = validate_workout(request.get_json(silent=True), allow_draft=True)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    if wid is None:
        wid = db.execute("INSERT INTO class_workouts(content) VALUES(?)",
                         (json.dumps(data),)).lastrowid
        status = 201
    else:
        db.execute("UPDATE class_workouts SET content=? WHERE id=?", (json.dumps(data), wid))
        status = 200
    db.commit()
    return jsonify(read_workout(db, wid)), status


@classes_bp.route("/api/workouts/<int:wid>", methods=["DELETE"])
def delete_workout(wid):
    db = get_db()
    if read_workout(db, wid) is None:
        return jsonify(error="Workout not found."), 404
    active = db.execute("SELECT workout_id FROM class_board_state WHERE id=1").fetchone()
    if active["workout_id"] == wid:
        return jsonify(error="Clear the class TV before deleting its template."), 409
    # Older previews may have dated slots; they no longer drive this manual board.
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='class_slots'").fetchone():
        db.execute("DELETE FROM class_slots WHERE workout_id=?", (wid,))
    db.execute("DELETE FROM class_workouts WHERE id=?", (wid,))
    db.commit()
    return jsonify(ok=True)


def valid_id(data, key):
    value = data.get(key)
    if type(value) is not int or value < 1:
        raise ValueError("Choose a saved workout.")
    return value


@classes_bp.route("/api/publish", methods=["POST"])
def publish():
    db = get_db()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Provide TV publishing settings."), 400
    if "workout_id" not in data:
        return jsonify(error="Choose a template, or explicitly clear the class TV."), 400
    wid = data.get("workout_id")
    expires = None
    content = None
    if wid is not None:
        try:
            valid_id(data, "workout_id")
            minutes = data.get("minutes", 90)
            if type(minutes) is not int or not 5 <= minutes <= 240:
                raise ValueError("Choose a display duration between 5 and 240 minutes.")
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        saved = read_workout(db, wid)
        if saved is None:
            return jsonify(error="Workout not found."), 404
        try:
            content = json.dumps(validate_workout(saved))
        except ValueError:
            return jsonify(error="Fill in every section's workout instructions before publishing."), 400
        expires = (now_local().astimezone(timezone.utc) + timedelta(minutes=minutes)).isoformat()
    db.execute("""UPDATE class_board_state SET workout_id=?, expires_at=?,
                  published_content=? WHERE id=1""", (wid, expires, content))
    db.commit()
    return jsonify(current_board(db))


def current_board(db):
    now = now_local()
    state = db.execute("SELECT * FROM class_board_state WHERE id=1").fetchone()
    if state["workout_id"] and datetime.fromisoformat(state["expires_at"]) > now:
        return {"workout": {"id": state["workout_id"], **json.loads(state["published_content"])},
                "mode": "manual",
                "until": state["expires_at"], "slot": None}
    if state["workout_id"]:
        db.execute(
            """UPDATE class_board_state SET workout_id=NULL, expires_at=NULL, published_content=NULL
               WHERE id=1 AND workout_id=? AND expires_at=?""",
            (state["workout_id"], state["expires_at"]),
        )
        db.commit()
    return {"workout": None, "mode": "standby", "until": None, "slot": None}


@classes_bp.route("/api/board")
def board():
    return jsonify(current_board(get_db()))
