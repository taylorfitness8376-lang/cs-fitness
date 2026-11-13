"""Automated pytest coverage for the CS Performance HYROX Race Simulation App (/hyrox)."""


def test_landing_page_includes_hyrox_card(client):
    """Landing hub page (/) includes the 3rd card for CS Performance HYROX Race Sim."""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "CS Performance HYROX Race Sim" in html
    assert "/hyrox/admin" in html
    assert "/hyrox/judge" in html
    assert "/hyrox/tv" in html


def test_seeded_demo_events_and_divisions_matrix(client):
    """Verify demo event seeding, 16-split sequence, and 7-division official HYROX weights matrix."""
    resp = client.get("/api/hyrox/events")
    assert resp.status_code == 200
    events = resp.get_json()
    assert len(events) >= 2
    nov_event = next(e for e in events if "Nov 2026" in e["name"])

    state_resp = client.get(f"/api/hyrox/events/{nov_event['id']}/state")
    assert state_resp.status_code == 200
    state = state_resp.get_json()

    assert len(state["splits_template"]) == 16
    assert state["splits_template"][0]["label"] == "Run 1"
    assert state["splits_template"][15]["station_key"] == "wall_balls"

    divisions = state["divisions"]
    assert set(divisions.keys()) == {
        "women_open",
        "women_pro",
        "men_open",
        "men_pro",
        "mixed_doubles",
        "women_doubles",
        "men_doubles",
    }
    assert divisions["men_open"]["wall_ball_target_reps"] == 100
    assert divisions["women_open"]["wall_ball_target_reps"] == 75
    assert "202 kg" in divisions["men_pro"]["stations"]["sled_push"]["prescription"]


def test_event_heat_creation_and_teamup_csv_import(client):
    """Test creating a new HYROX Sim event, generating waves, and importing a TeamUp CSV."""
    sample_resp = client.get("/api/hyrox/sample-csv")
    assert sample_resp.status_code == 200
    assert "First Name,Last Name,Email" in sample_resp.data.decode("utf-8")

    ev_resp = client.post(
        "/api/hyrox/events",
        json={
            "name": "CS Performance Spring HYROX Sim",
            "event_date": "2027-03-14",
            "venue": "CS Performance Main Floor",
            "wave_interval_mins": 15,
            "lanes_per_wave": 4,
            "first_wave_time": "08:00",
            "num_waves": 3,
        },
    )
    assert ev_resp.status_code in (200, 201)
    event_id = ev_resp.get_json()["id"]

    csv_text = (
        "First Name,Last Name,Email,DOB,Division,Partner Name,Heat Time,Volunteer\n"
        "Alex,Mercer,alex@csfitness.co.uk,1993-06-15,Men Pro,,08:00,Coach Dan\n"
        "Hannah,Cole,hannah@csfitness.co.uk,1997-02-10,Women Open,,08:15,Coach Maya\n"
        "Tom,Wright,tom@csfitness.co.uk,1989-11-20,Mixed Doubles,Lucy Wright,08:30,Coach Dan\n"
    )
    imp_resp = client.post(
        f"/api/hyrox/events/{event_id}/import-csv",
        json={"csv_text": csv_text},
    )
    assert imp_resp.status_code == 200
    imp_data = imp_resp.get_json()
    assert imp_data["imported_count"] == 3

    state = client.get(f"/api/hyrox/events/{event_id}/state").get_json()
    entries = state["entries"]
    assert len(entries) == 3
    alex = next(e for e in entries if "Alex Mercer" in e["display_name"])
    assert alex["division"] == "men_pro"
    assert alex["age_category"] in ("30-34", "35-39")
    assert len(alex["splits"]) == 16
    assert len(alex["judge_pin"]) == 4


def test_volunteer_16_split_progression_undo_and_wall_balls(client):
    """Test starting an entry, advancing through all 16 splits, undo, and Wall Ball rep counter."""
    events = client.get("/api/hyrox/events").get_json()
    event_id = events[0]["id"]

    create_resp = client.post(
        f"/api/hyrox/events/{event_id}/entries",
        json={
            "display_name": "Test Racer",
            "email": "racer@csfitness.co.uk",
            "division": "men_open",
            "age_category": "30-34",
            "volunteer_name": "Volunteer Sam",
        },
    )
    assert create_resp.status_code in (200, 201)
    entry = create_resp.get_json()
    entry_id = entry["id"]

    # Lookup by Judge PIN
    pin_resp = client.post("/api/hyrox/judge/lookup", json={"judge_pin": entry["judge_pin"]})
    assert pin_resp.status_code == 200
    assert pin_resp.get_json()["entry"]["id"] == entry_id

    # Start race at t = 1,000,000 ms
    t0 = 1_000_000
    start_resp = client.post(f"/api/hyrox/entries/{entry_id}/start", json={"started_at_ms": t0, "force": True})
    assert start_resp.status_code == 200
    assert start_resp.get_json()["entry"]["status"] == "racing"

    # Advance Split 1 (Run 1: 4m 00s = 240,000ms)
    r1 = client.post(
        f"/api/hyrox/entries/{entry_id}/advance",
        json={"timestamp_ms": t0 + 240_000},
    ).get_json()["entry"]
    assert r1["completed_splits"] == 1
    assert r1["run_total_ms"] == 240_000

    # Undo Split 1
    undo_entry = client.post(f"/api/hyrox/entries/{entry_id}/undo").get_json()["entry"]
    assert undo_entry["completed_splits"] == 0
    assert (undo_entry["run_total_ms"] or 0) == 0

    # Complete all 16 splits sequentially
    cur_t = t0
    for idx in range(1, 17):
        cur_t += 180_000 if idx % 2 == 1 else 150_000
        adv = client.post(
            f"/api/hyrox/entries/{entry_id}/advance",
            json={"timestamp_ms": cur_t},
        ).get_json()["entry"]

    # Update Wall Ball reps
    wb_res = client.post(
        f"/api/hyrox/entries/{entry_id}/wall-balls",
        json={"delta": 100},
    ).get_json()
    assert wb_res["wall_ball_reps"] == 100
    assert adv["status"] == "finished"
    assert adv["completed_splits"] == 16
    assert adv["run_total_ms"] == 8 * 180_000
    assert adv["station_total_ms"] == 8 * 150_000
    assert adv["total_ms"] == 8 * 330_000


def test_split_corrections_and_combined_segment_splitter(client):
    """Test Race Director split corrections and splitting a combined Run+Station segment."""
    events = client.get("/api/hyrox/events").get_json()
    event_id = events[0]["id"]
    state = client.get(f"/api/hyrox/events/{event_id}/state").get_json()
    ewan = next(e for e in state["entries"] if "Ewan Taylor" in e["display_name"])
    entry_id = ewan["id"]

    # Edit Split 1 and add a 15s penalty
    corr_resp = client.put(
        f"/api/hyrox/entries/{entry_id}/splits",
        json={
            "splits": [{"split_index": 1, "duration_str": "03:50"}],
            "penalty_str": "00:15",
            "edited_by": "race_director",
        },
    )
    assert corr_resp.status_code == 200
    updated = corr_resp.get_json()["entry"]
    s1 = next(s for s in updated["splits"] if s["split_index"] == 1)
    assert s1["duration_ms"] == 230_000
    assert updated["penalty_ms"] == 15_000

    # Split a combined 07:30 segment across Split 1 (04:00) and Split 2 (remainder 03:30)
    comb_resp = client.put(
        f"/api/hyrox/entries/{entry_id}/splits",
        json={
            "split_combined": {
                "first_split_index": 1,
                "combined_duration_str": "07:30",
                "first_duration_str": "04:00",
            }
        },
    )
    assert comb_resp.status_code == 200
    comb_entry = comb_resp.get_json()["entry"]
    s1_after = next(s for s in comb_entry["splits"] if s["split_index"] == 1)
    s2_after = next(s for s in comb_entry["splits"] if s["split_index"] == 2)
    assert s1_after["duration_ms"] == 240_000
    assert s2_after["duration_ms"] == 210_000


def test_historical_progression_and_web_surfaces(client):
    """Verify Roxfit-Lite historical comparison for Ewan Taylor and HTML surfaces."""
    events = client.get("/api/hyrox/events").get_json()
    nov_event = next(e for e in events if "Nov 2026" in e["name"])
    state = client.get(f"/api/hyrox/events/{nov_event['id']}/state").get_json()
    ewan = next(e for e in state["entries"] if "Ewan Taylor" in e["display_name"])

    assert ewan["history"] is not None
    assert ewan["history"]["sim_count"] >= 2
    assert ewan["history"]["comparison"] is not None
    assert ewan["history"]["comparison"]["total_delta_ms"] < 0

    # Surface 1: Sim Management & Race Director Console
    root_hyrox_resp = client.get("/hyrox")
    assert root_hyrox_resp.status_code == 200
    assert b"RACE DIRECTOR CONSOLE" in root_hyrox_resp.data

    admin_resp = client.get("/hyrox/admin")
    assert admin_resp.status_code == 200
    assert b"TEAMUP CSV IMPORT" in admin_resp.data

    # Surface 2: Volunteer Judge App
    judge_resp = client.get(f"/hyrox/judge?entry={ewan['id']}")
    assert judge_resp.status_code == 200
    assert b"Wall Ball Rep Counter" in judge_resp.data

    # Surface 3: Live Gym TV Broadcast
    tv_resp = client.get("/hyrox/tv")
    assert tv_resp.status_code == 200
    assert b"LIVE ON-FLOOR TRACKER" in tv_resp.data

    # Surface 4: Athlete Results & Social Finisher Card
    res_resp = client.get(f"/hyrox/results/{ewan['id']}")
    assert res_resp.status_code == 200
    assert b"FINISHER CARD GENERATOR" in res_resp.data

    ath_resp = client.get(f"/hyrox/athlete/{ewan['athlete_id']}")
    assert ath_resp.status_code == 200
    assert b"Ewan Taylor" in ath_resp.data
