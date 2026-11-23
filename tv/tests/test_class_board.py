from datetime import datetime
from zoneinfo import ZoneInfo

import pytest


@pytest.fixture
def coach(authed_client):
    response = authed_client.get("/classes/api/planner")
    assert response.status_code == 200
    token = response.get_json()["csrf_token"]
    authed_client.environ_base["HTTP_X_CSRF_TOKEN"] = token
    return authed_client


def workout(client, title="Partner workout"):
    return client.post("/classes/api/workouts", json={
        "title": title,
        "class_type": "HYROX",
        "notes": "Teams of 2 - share anyhow",
        "sections": [
            {"title": "Buy in", "body": "80 cal Row / Ski\nSwitch every 10 burpees"},
            {"title": "Main workout", "body": "100 DB dual squats\n20 SA Devil Press synchro"},
        ],
    })


def test_class_admin_auth_and_csrf(client):
    assert client.get("/classes").status_code == 302
    assert client.get("/classes/api/planner").status_code == 401
    assert client.get("/classes/api/preview/1").status_code == 401
    with client.session_transaction() as state:
        state["authed"] = True
    assert workout(client).status_code == 403
    assert client.get("/classes/display").status_code == 200
    assert client.get("/classes/api/board").status_code == 200


def test_class_login_returns_to_planner_without_open_redirect(client):
    response = client.post("/login?next=/classes", data={"password": "csfit2024"})
    assert response.headers["Location"] == "/classes"
    response = client.post("/login?next=https://example.com", data={"password": "csfit2024"})
    assert response.headers["Location"] == "/cms"


def test_planner_shows_notes_without_template_options_or_exercise_picker(coach):
    response = coach.get("/classes")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="class-select"' in html
    assert 'name="notes"' in html
    assert "<details" not in html
    assert "Workout instructions" in html
    assert 'id="save-workout"' in html
    assert 'id="save-publish"' in html
    for removed in ("Template details", "New template", "Copy template",
                    "Delete template", "Add exercise", "exercise-picker",
                    "class_exercises.js"):
        assert removed not in html


def test_workout_roundtrip_and_validation(coach):
    created = workout(coach)
    assert created.status_code == 201
    saved = created.get_json()
    assert saved["sections"][1]["body"].endswith("synchro")
    assert coach.put(f"/classes/api/workouts/{saved['id']}", json={
        **saved, "title": "Updated",
    }).status_code == 200
    library = coach.get("/classes/api/planner").get_json()["workouts"]
    assert any(item["title"] == "Updated" for item in library)
    assert coach.post("/classes/api/workouts", json={"title": "Empty"}).status_code == 400
    assert coach.post("/classes/api/workouts", json=[]).status_code == 400
    assert coach.delete(f"/classes/api/workouts/{saved['id']}").status_code == 200


def test_publishing_is_a_snapshot_and_does_not_change_gym_tv(coach):
    existing_tv = coach.get("/api/session").get_json()
    saved = workout(coach).get_json()
    wid = saved["id"]
    assert coach.post("/classes/api/publish", json={"workout_id": wid}).status_code == 200
    coach.put(f"/classes/api/workouts/{wid}", json={**saved, "title": "Unpublished edit"})
    assert coach.get("/classes/api/board").get_json()["workout"]["title"] == saved["title"]
    assert coach.get("/api/session").get_json() == existing_tv
    assert coach.post("/classes/api/publish", json={"workout_id": wid}).status_code == 200
    assert coach.get("/classes/api/board").get_json()["workout"]["title"] == "Unpublished edit"
    assert coach.post("/classes/api/publish", json={"workout_id": None}).status_code == 200
    assert coach.get("/classes/api/board").get_json()["workout"] is None


def test_manual_publish_expires_to_standby(coach, monkeypatch):
    import class_board
    now = datetime(2026, 11, 22, 10, 0, tzinfo=ZoneInfo("Europe/London"))
    monkeypatch.setattr(class_board, "now_local", lambda: now)
    wid = workout(coach).get_json()["id"]
    assert coach.post("/classes/api/publish", json={
        "workout_id": wid, "minutes": 30,
    }).status_code == 200
    assert coach.get("/classes/api/board").get_json()["mode"] == "manual"
    monkeypatch.setattr(class_board, "now_local", lambda: now.replace(minute=30))
    assert coach.get("/classes/api/board").get_json()["workout"] is None
    assert coach.post("/classes/api/publish", json={"workout_id": 999999}).status_code == 404
    assert coach.post("/classes/api/publish", json={"workout_id": wid, "minutes": -1}).status_code == 400
    assert coach.post("/classes/api/publish", json={}).status_code == 400


def test_override_duration_is_elapsed_time_across_clock_change(coach, monkeypatch):
    import class_board
    monkeypatch.setattr(class_board, "now_local", lambda:
                        datetime(2026, 10, 25, 1, 30, tzinfo=ZoneInfo("Europe/London")))
    wid = workout(coach).get_json()["id"]
    response = coach.post("/classes/api/publish", json={"workout_id": wid, "minutes": 90})
    assert response.get_json()["until"] == "2026-10-25T02:00:00+00:00"


def test_samples_are_drafts_and_initialization_is_idempotent(coach):
    first = coach.get("/classes/api/planner").get_json()
    second = coach.get("/classes/api/planner").get_json()
    assert len(first["workouts"]) == len(second["workouts"]) == 13
    assert "slots" not in first
    assert coach.get("/classes/api/board").get_json()["workout"] is None


def test_blank_class_templates_can_be_saved_but_not_published(coach):
    templates = coach.get("/classes/api/planner").get_json()["workouts"]
    template = next(row for row in templates if row["class_type"] == "Metcon")
    assert template["sections"] == [{"title": "Main workout", "body": ""}]
    wid = template["id"]
    assert coach.post("/classes/api/publish", json={"workout_id": wid}).status_code == 400
    template["notes"] = "Coach draft"
    assert coach.put(f"/classes/api/workouts/{wid}", json=template).status_code == 200
    template["sections"][0]["body"] = "Coach-programmed workout"
    assert coach.put(f"/classes/api/workouts/{wid}", json=template).status_code == 200
    assert coach.post("/classes/api/publish", json={"workout_id": wid}).status_code == 200


def test_existing_preview_migrates_without_overwriting_coach_templates(app, authed_client):
    import json
    from datetime import timedelta
    from class_board import now_local
    from database import get_db

    content = {
        "title": "Coach's EMOM", "class_type": "EMOM", "notes": "",
        "sections": [{"title": "Main workout", "body": "Existing coach instructions"}],
    }
    with app.app_context():
        db = get_db()
        db.execute("CREATE TABLE class_workouts(id INTEGER PRIMARY KEY, content TEXT NOT NULL)")
        db.execute("""CREATE TABLE class_board_state(
            id INTEGER PRIMARY KEY, workout_id INTEGER, expires_at TEXT, seeded INTEGER)""")
        db.execute("INSERT INTO class_workouts VALUES(1,?)", (json.dumps(content),))
        db.execute("INSERT INTO class_board_state VALUES(1,1,?,1)",
                   ((now_local() + timedelta(hours=1)).isoformat(),))
        db.commit()
    data = authed_client.get("/classes/api/planner").get_json()
    assert len(data["workouts"]) == 13
    assert next(row for row in data["workouts"] if row["id"] == 1)["title"] == "Coach's EMOM"
    assert data["board"]["workout"]["title"] == "Coach's EMOM"
    with app.app_context():
        db = get_db()
        content["title"] = "Unpublished migrated edit"
        db.execute("UPDATE class_workouts SET content=? WHERE id=1", (json.dumps(content),))
        db.commit()
    assert authed_client.get("/classes/api/board").get_json()["workout"]["title"] == "Coach's EMOM"
