def test_login_redirects_to_cms_on_correct_password(client):
    response = client.post("/login", data={"password": "csfit2024"},
                           follow_redirects=False)
    assert response.status_code == 302
    assert "/cms" in response.headers["Location"]

def test_login_rejects_wrong_password(client):
    response = client.post("/login", data={"password": "wrong"})
    assert response.status_code == 200
    assert b"Incorrect password" in response.data

def test_cms_requires_auth(client):
    response = client.get("/cms", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

def test_cms_accessible_when_authed(authed_client):
    response = authed_client.get("/cms")
    assert response.status_code == 200

def test_logout_clears_session(authed_client):
    authed_client.post("/logout")
    response = authed_client.get("/cms", follow_redirects=False)
    assert response.status_code == 302

# ── Sessions ──────────────────────────────────────────────

def test_create_session(authed_client):
    payload = {
        "name": "Full Body Strength",
        "coach_notes": "Rest 90s between sets.",
        "blocks": [
            {
                "label": "A",
                "focus": "Strength / Power",
                "exercises": [
                    {"code": "A1", "name": "Back Squat", "sets_reps": "4×8"},
                    {"code": "A2", "name": "Box Jump",   "sets_reps": "4×4"},
                ]
            }
        ]
    }
    r = authed_client.post("/api/sessions", json=payload)
    assert r.status_code == 201
    data = r.get_json()
    assert data["id"] is not None
    assert data["name"] == "Full Body Strength"

def test_list_sessions(authed_client):
    authed_client.post("/api/sessions", json={
        "name": "Session X", "coach_notes": "", "blocks": []
    })
    r = authed_client.get("/api/sessions")
    assert r.status_code == 200
    assert len(r.get_json()) >= 1

def test_get_session_includes_blocks_and_exercises(authed_client):
    r = authed_client.post("/api/sessions", json={
        "name": "Test",
        "coach_notes": "notes",
        "blocks": [{"label": "A", "focus": "Power",
                    "exercises": [{"code": "A1", "name": "Squat", "sets_reps": "4×8"}]}]
    })
    sid = r.get_json()["id"]
    r2 = authed_client.get(f"/api/sessions/{sid}")
    data = r2.get_json()
    assert len(data["blocks"]) == 1
    assert data["blocks"][0]["label"] == "A"
    assert data["blocks"][0]["exercises"][0]["name"] == "Squat"

def test_delete_session(authed_client):
    r = authed_client.post("/api/sessions", json={
        "name": "To Delete", "coach_notes": "", "blocks": []
    })
    sid = r.get_json()["id"]
    authed_client.delete(f"/api/sessions/{sid}")
    r2 = authed_client.get(f"/api/sessions/{sid}")
    assert r2.status_code == 404

def test_update_session(authed_client):
    r = authed_client.post("/api/sessions", json={
        "name": "Old Name", "coach_notes": "", "blocks": []
    })
    sid = r.get_json()["id"]
    authed_client.put(f"/api/sessions/{sid}", json={
        "name": "New Name", "coach_notes": "updated", "blocks": []
    })
    r2 = authed_client.get(f"/api/sessions/{sid}")
    assert r2.get_json()["name"] == "New Name"


def test_display_and_sw_routes(client):
    r = client.get("/display")
    assert r.status_code == 200
    assert b"INITIAL_SESSION" in r.data
    assert b"#root { flex: 1; display: flex;" in r.data

    sw = client.get("/sw-display.js")
    assert sw.status_code == 200
    assert b"cs-fitness-tv-v2" in sw.data


def test_default_tv_sessions_auto_seed(app, client):
    from database import get_db, seed_default_tv_sessions
    with app.app_context():
        db = get_db()
        seed_default_tv_sessions(db)
        db.commit()
    r = client.get("/api/session")
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("name") is not None
    assert "CS Performance" in data["name"]

