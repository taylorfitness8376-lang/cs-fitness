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
    """Verify default weekend event starts with zero sample data, 16-split sequence, and 9-division matrix."""
    resp = client.get("/api/hyrox/events")
    assert resp.status_code == 200
    events = resp.get_json()
    assert len(events) >= 1
    nov_event = next(e for e in events if "Nov 2026" in e["name"] or "28th" in e["name"])

    state_resp = client.get(f"/api/hyrox/events/{nov_event['id']}/state")
    assert state_resp.status_code == 200
    state = state_resp.get_json()

    # No sample/fake athletes or entries are pre-seeded
    assert state["entries"] == []

    assert len(state["splits_template"]) == 16
    assert state["splits_template"][0]["label"].startswith("Run 1")
    assert state["splits_template"][15]["station_key"] == "wall_balls"

    divisions = state["divisions"]
    assert set(divisions.keys()) == {
        "women_open",
        "women_doubles",
        "women_pro",
        "women_pro_doubles",
        "men_open",
        "men_doubles",
        "mixed_doubles",
        "men_pro",
        "men_pro_doubles",
    }
    assert divisions["men_open"]["wall_ball_target_reps"] == 100
    assert divisions["women_open"]["wall_ball_target_reps"] == 75
    assert "202 kg" in divisions["men_pro"]["stations"]["sled_push"]["prescription"]
    assert "202 kg" in divisions["men_pro_doubles"]["stations"]["sled_push"]["prescription"]
    assert "152 kg" in divisions["women_pro_doubles"]["stations"]["sled_push"]["prescription"]

    # Verify 2-day event & 1-racer-per-slot heats + weight changeover annotations
    assert state["event"]["num_days"] == 2
    heats = state["heats"]
    assert any(h.get("day_number") == 1 for h in heats)
    assert any(h.get("day_number") == 2 for h in heats)
    assert all(h.get("max_lanes") == 1 for h in heats)
    assert any(h.get("weight_change_from_prev") is True and h.get("weight_change_alert") for h in heats)


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

    # Simulate completing Splits 1..4 + accidental tap on Split 5, then Undo Last Split
    # Even if client sends explicit undone_split_index + remaining_splits, only Split 5 is cleared
    remaining_after_undo_5 = [
        {"split_index": 1, "duration_ms": 210_000, "completed_at_ms": t0 + 210_000},
        {"split_index": 2, "duration_ms": 195_000, "completed_at_ms": t0 + 405_000},
        {"split_index": 3, "duration_ms": 220_000, "completed_at_ms": t0 + 625_000},
        {"split_index": 4, "duration_ms": 180_000, "completed_at_ms": t0 + 805_000},
    ]
    adv_5 = client.post(
        f"/api/hyrox/entries/{entry_id}/advance",
        json={
            "action": "split",
            "split_index": 5,
            "duration_ms": 2_000,
            "completed_at_ms": t0 + 807_000,
            "timestamp_ms": t0 + 807_000,
            "started_at_ms": t0,
            "splits_state": remaining_after_undo_5 + [
                {"split_index": 5, "duration_ms": 2_000, "completed_at_ms": t0 + 807_000}
            ],
        },
    ).get_json()["entry"]
    assert adv_5["completed_splits"] == 5
    assert adv_5["current_split_index"] == 6

    # Undo Split 5 -> must keep Splits 1..4 intact and move back to Split 5
    undo_5 = client.post(
        f"/api/hyrox/entries/{entry_id}/undo",
        json={
            "undone_split_index": 5,
            "started_at_ms": t0,
            "remaining_splits": remaining_after_undo_5,
        },
    ).get_json()["entry"]
    assert undo_5["status"] == "racing"
    assert undo_5["completed_splits"] == 4
    assert undo_5["current_split_index"] == 5
    assert undo_5["splits"][0]["duration_ms"] == 210_000
    assert undo_5["splits"][1]["duration_ms"] == 195_000
    assert undo_5["splits"][2]["duration_ms"] == 220_000
    assert undo_5["splits"][3]["duration_ms"] == 180_000
    assert undo_5["splits"][4]["duration_ms"] is None

    # Reset back to racing at t0 with 0 splits before testing full 16-split loop
    for idx in (4, 3, 2, 1):
        u_res = client.post(
            f"/api/hyrox/entries/{entry_id}/undo",
            json={"undone_split_index": idx, "started_at_ms": t0, "remaining_splits": remaining_after_undo_5[: idx - 1]},
        ).get_json()["entry"]
        assert u_res["completed_splits"] == idx - 1

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
    create_resp = client.post(
        f"/api/hyrox/events/{event_id}/entries",
        json={"display_name": "Split Edit Athlete", "division": "men_open"},
    )
    assert create_resp.status_code == 201
    entry_id = create_resp.get_json()["id"]

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
    """Verify Roxfit-Lite historical comparison across 2 sims and HTML surfaces."""
    ev1 = client.post(
        "/api/hyrox/events",
        json={"name": "Baseline Sim", "event_date": "2026-09-19", "first_wave_time": "09:00", "num_waves": 2},
    ).get_json()
    ev2 = client.post(
        "/api/hyrox/events",
        json={"name": "Second Sim", "event_date": "2026-11-28", "first_wave_time": "14:00", "num_waves": 2},
    ).get_json()

    e1 = client.post(
        f"/api/hyrox/events/{ev1['id']}/entries",
        json={"display_name": "Ewan Taylor", "email": "ewan@csfitness.co.uk", "division": "men_open"},
    ).get_json()
    client.put(
        f"/api/hyrox/entries/{e1['id']}/splits",
        json={
            "status": "finished",
            "splits": [{"split_index": i, "duration_str": "04:00"} for i in range(1, 17)],
        },
    )

    e2 = client.post(
        f"/api/hyrox/events/{ev2['id']}/entries",
        json={"display_name": "Ewan Taylor", "email": "ewan@csfitness.co.uk", "division": "men_open"},
    ).get_json()
    client.put(
        f"/api/hyrox/entries/{e2['id']}/splits",
        json={
            "status": "finished",
            "splits": [{"split_index": i, "duration_str": "03:45"} for i in range(1, 17)],
        },
    )

    state = client.get(f"/api/hyrox/events/{ev2['id']}/state").get_json()
    ewan = next(e for e in state["entries"] if "Ewan Taylor" in e["display_name"])

    assert ewan["history"] is not None
    assert ewan["history"]["sim_count"] >= 2
    assert ewan["history"]["comparison"] is not None
    assert ewan["history"]["comparison"]["total_delta_ms"] < 0
    assert ewan["avg_run_rank"] >= 1
    assert ewan["splits"][1]["roxfit_label"] == "Ski"
    assert any(s.get("is_pb") for s in ewan["splits"])

    # Surface 1: Sim Management & Race Director Console
    root_hyrox_resp = client.get("/hyrox")
    assert root_hyrox_resp.status_code == 200
    assert b"HYROX SIM \xc2\xb7 RACE DIRECTOR" in root_hyrox_resp.data
    assert b"/static/logo.jpg" in root_hyrox_resp.data

    admin_resp = client.get("/hyrox/admin")
    assert admin_resp.status_code == 200
    assert b"ATHLETES &amp; RESULTS" in admin_resp.data
    assert b"1. Event Setup" in admin_resp.data
    assert b"2. Add Athlete(s)" in admin_resp.data
    assert b"3. Event" in admin_resp.data
    assert b"Add Athlete / Pair" not in admin_resp.data
    assert b"FAST ADD ATHLETE / PAIR &amp; BULK PASTE LIST" not in admin_resp.data
    assert b"signup-groups-board" not in admin_resp.data
    assert b"DIVISION &amp; EQUIPMENT CHANGEOVER" not in admin_resp.data
    assert b'id="modal-division"' in admin_resp.data
    assert b'<option value="men_doubles">Men&#39;s Open Doubles (M Open Dbl)</option>' in admin_resp.data
    assert b'<option value="mixed_doubles">Mixed Doubles (Mixed Dbl)</option>' in admin_resp.data
    assert b'<option value="women_pro_doubles">Female Pro Doubles (F Pro Dbl)</option>' in admin_resp.data
    assert b'href="/hyrox/judge"' in admin_resp.data
    assert b'href="/hyrox/tv"' in admin_resp.data
    assert b'href="/hyrox/tv/finisher"' in admin_resp.data
    assert b'href="/"' in admin_resp.data
    assert b"CS Hub" in admin_resp.data
    assert b'href="/cms"' not in admin_resp.data
    assert b'href="/challenge"' not in admin_resp.data
    assert b"Age Category" not in admin_resp.data
    assert b"copyResultWebLink" not in admin_resp.data
    assert b"athlete@email.com" not in admin_resp.data
    assert b'id="filter-search"' not in admin_resp.data
    assert b'title="Judge Timer"' not in admin_resp.data
    assert b'title="Results &amp; Social Card"' not in admin_resp.data

    # Surface 2: Volunteer Judge App (Direct Athlete Selector + Top Run Pace Strip)
    judge_resp = client.get(f"/hyrox/judge?entry={ewan['id']}")
    assert judge_resp.status_code == 200
    assert b"Wall Ball Rep Counter" in judge_resp.data
    assert b"UNBROKEN" in judge_resp.data
    assert b"Avg Run Pace" in judge_resp.data
    assert b"/static/logo.jpg" in judge_resp.data
    assert b'href="/"' in judge_resp.data
    assert b"CS Hub" in judge_resp.data

    # Surface 3A: TV 1 — Live Timings TV (/hyrox/tv)
    tv_resp = client.get("/hyrox/tv")
    assert tv_resp.status_code == 200
    assert b"LIVE TIMINGS" in tv_resp.data
    assert b"START LIST" in tv_resp.data
    assert b'href="/"' in tv_resp.data
    assert b"CS Hub" in tv_resp.data
    assert b"LIVE ON-FLOOR TIMINGS" not in tv_resp.data
    assert b"Single-Screen Rolling Broadcast" not in tv_resp.data
    assert b"tv-spotlight-select" not in tv_resp.data
    assert b"TV 2: Finisher Shot" not in tv_resp.data
    assert b"/hyrox/admin" not in tv_resp.data
    assert b"/static/logo.jpg" in tv_resp.data
    assert b"DIVISION LEADERBOARD" not in tv_resp.data

    # Surface 3B: TV 2 — Finisher Social Shot TV (/hyrox/tv/finisher)
    tv_fin_resp = client.get(f"/hyrox/tv/finisher?entry={ewan['id']}")
    assert tv_fin_resp.status_code == 200
    assert b"/static/logo.jpg" in tv_fin_resp.data
    assert b"CS <span>FITNESS</span>" in tv_fin_resp.data
    assert b"TRAIN HARD &amp; BE SOUND" in tv_fin_resp.data
    assert b"HYROX SIM" in tv_fin_resp.data
    assert b"OFFICIAL FINISHER TIME" in tv_fin_resp.data
    assert b"CS Hub" in tv_fin_resp.data

    # Surface 4: Athlete Results & Social Finisher Card
    res_resp = client.get(f"/hyrox/results/{ewan['id']}")
    assert res_resp.status_code == 200
    assert b"CS FITNESS <span>HYROX SIM</span> FINISHER ANALYTICS" in res_resp.data
    assert b"SOCIAL MEDIA FINISHER SHOT" in res_resp.data
    assert b"Clean Finisher Social Shot" in res_resp.data
    assert b"Detailed 16-Split Breakdown" in res_resp.data
    assert b"/static/logo.jpg" in res_resp.data
    assert b"Train Hard &amp; Be Sound" in res_resp.data
    assert b'href="/cms"' not in res_resp.data
    assert b'href="/hyrox/admin"' not in res_resp.data
    assert b"Age Cat" not in res_resp.data

    ath_resp = client.get(f"/hyrox/athlete/{ewan['athlete_id']}")
    assert ath_resp.status_code == 200
    assert b"Ewan Taylor" in ath_resp.data


def test_simplified_entry_pair_splitting_bulk_paste_and_clear(client):
    """Test 1-line pair name splitting, auto-slot assignment, bulk paste list, and clear-entries."""
    ev_resp = client.post(
        "/api/hyrox/events/setup-weekend",
        json={"saturday_date": "2026-11-28", "sunday_date": "2026-11-29", "sync_teamup": False},
    )
    assert ev_resp.status_code in (200, 201)
    event_id = ev_resp.get_json()["event"]["id"]

    # 1. Single-line pair entry with '&' auto-splits partner and auto-assigns Group 2 (Sat 15:30)
    pair_resp = client.post(
        f"/api/hyrox/events/{event_id}/entries",
        json={"display_name": "Luke Shaw & Dan Reid", "signup_group": "male_mixed_doubles"},
    )
    assert pair_resp.status_code == 201
    pair_entry = pair_resp.get_json()
    assert pair_entry["display_name"] == "Luke Shaw"
    assert pair_entry["partner_name"] == "Dan Reid"
    assert pair_entry["division"] == "men_doubles"
    assert pair_entry["heat_day_number"] == 1
    assert pair_entry["heat_start_time"] == "15:30"

    # 2. Bulk paste list with multiple lines across formats
    bulk_resp = client.post(
        f"/api/hyrox/events/{event_id}/entries/bulk-simple",
        json={
            "division": "women_open",
            "lines_text": (
                "10:00 Hannah Millar\n"
                "Chloe Grant & Sophie Robertson | Female Doubles | 12:10 | Coach Laura\n"
                "10:20 Emma Kerr, Coach Chris\n"
            ),
        },
    )
    assert bulk_resp.status_code == 201
    bulk_data = bulk_resp.get_json()
    assert bulk_data["added_count"] == 3
    groups_map = {g["key"]: g for g in bulk_data["signup_groups"]}
    assert groups_map["male_mixed_doubles"]["count"] == 1
    assert groups_map["female_solo"]["count"] == 2
    assert groups_map["female_doubles"]["count"] == 1

    # 3. Clear all entries resets the event cleanly back to 0 entries
    clear_resp = client.post(f"/api/hyrox/events/{event_id}/clear-entries")
    assert clear_resp.status_code == 200
    assert clear_resp.get_json()["deleted_count"] == 4
    state_after = client.get(f"/api/hyrox/events/{event_id}/state").get_json()
    assert state_after["entries"] == []


def test_teamup_api_v2_sync_and_webhooks(client):
    """Test TeamUp REST API v2 config, attendance expansion sync, idempotent upsert, and webhook receiver."""
    # 1. Check status & save config
    st_resp = client.get("/api/hyrox/teamup/status")
    assert st_resp.status_code == 200
    st_data = st_resp.get_json()
    assert st_data["api_spec"]["base_url"] == "https://goteamup.com/api/v2"

    cfg_resp = client.post(
        "/api/hyrox/teamup/config",
        json={
            "api_token": "Bearer tu_m2m_test_token_12345678",
            "provider_id": "285151",
            "webhook_secret": "cs_secret_99",
        },
    )
    assert cfg_resp.status_code == 200
    cfg_json = cfg_resp.get_json()
    assert cfg_json["configured"] is True
    assert cfg_json["provider_id"] == "285151"
    assert "••••" in cfg_json["masked_token"]

    # 2. Sync a TeamUp v2 /api/v2/attendances?expand=event,customer payload into a fresh Sim event
    ev_resp = client.post(
        "/api/hyrox/events",
        json={
            "name": "CS Performance HYROX Sim — TeamUp API Sync Test",
            "event_date": "2026-12-12",
            "first_wave_time": "09:00",
            "num_waves": 2,
            "wave_interval_mins": 15,
            "lanes_per_wave": 4,
        },
    )
    event_id = ev_resp.get_json()["id"]

    teamup_v2_payload = {
        "count": 2,
        "next": None,
        "previous": None,
        "results": [
            {
                "id": 9001,
                "status": "registered",
                "customer": {
                    "id": 818974,
                    "first_name": "Rory",
                    "last_name": "MacDonald",
                    "email": "rory.macdonald@example.com",
                    "date_of_birth": "1990-06-15",
                },
                "event": {
                    "id": 14947247,
                    "name": "HYROX Sim — Men Pro Wave",
                    "local_starts_at": "2026-12-12T09:00:00",
                    "offering_type": {"id": 55, "name": "HYROX Men Pro"},
                    "instructors": [{"id": 12, "name": "Coach Chris"}],
                },
            },
            {
                "id": 9002,
                "status": "registered",
                "customer": {
                    "id": 818975,
                    "name": "Chloe & Sophie",
                    "email": "chloe.sophie@example.com",
                    "date_of_birth": "1995-03-20",
                    "custom_fields": {
                        "division": "Women Doubles",
                        "partner_name": "Sophie Robertson",
                    },
                },
                "event": {
                    "id": 14947248,
                    "name": "HYROX Sim — 09:15 Wave",
                    "starts_at": "2026-12-12T09:15:00Z",
                },
            },
        ],
    }

    sync_resp = client.post(
        f"/api/hyrox/events/{event_id}/sync-teamup",
        json=teamup_v2_payload,
    )
    assert sync_resp.status_code == 200
    sync_data = sync_resp.get_json()
    assert sync_data["synced_count"] == 2

    # Re-syncing the exact same payload should be idempotent (updates in place, still 2 entries total)
    resync_resp = client.post(
        f"/api/hyrox/events/{event_id}/sync-teamup",
        json=teamup_v2_payload,
    )
    assert resync_resp.status_code == 200
    state = client.get(f"/api/hyrox/events/{event_id}/state").get_json()
    assert len(state["entries"]) == 2
    rory = next(e for e in state["entries"] if "Rory MacDonald" in e["display_name"])
    assert rory["division"] == "men_pro"
    assert rory["age_category"] == "35-39"
    assert rory["heat_start_time"] == "09:00"
    assert rory["volunteer_name"] == "Coach Chris"

    # 3. Test TeamUp v2 Webhook receiver (with secret + TEAMUP-WEBHOOK-ID deduplication)
    bad_wh = client.post(
        f"/api/hyrox/teamup/webhook?event_id={event_id}&secret=wrong",
        json={"feed_items": []},
    )
    assert bad_wh.status_code == 403

    wh_payload = {
        "feed_items": [
            {
                "id": 501,
                "type": "event_registration.late_cancelled",
                "resources": {"customer": 818974, "event": 14947247, "business": 285151},
            }
        ]
    }
    wh_resp = client.post(
        f"/api/hyrox/teamup/webhook?event_id={event_id}&secret=cs_secret_99",
        headers={"TEAMUP-WEBHOOK-ID": "tu-wh-uuid-001"},
        json=wh_payload,
    )
    assert wh_resp.status_code == 200
    wh_json = wh_resp.get_json()
    assert wh_json["deduplicated"] is False
    assert wh_json["processed_count"] == 1

    # 4. Edit an imported single athlete to add a Doubles partner, change division, age group, volunteer, and custom 1:1 slot
    edit_resp = client.put(
        f"/api/hyrox/entries/{rory['id']}",
        json={
            "display_name": "Rory MacDonald",
            "partner_name": "Kirsty Stewart",
            "division": "mixed_doubles",
            "age_category": "40-44",
            "volunteer_name": "Coach Emma",
            "custom_slot_day": 2,
            "custom_slot_time": "09:40",
        },
    )
    assert edit_resp.status_code == 200
    edited_entry = edit_resp.get_json()
    assert edited_entry["partner_name"] == "Kirsty Stewart"
    assert edited_entry["full_display_name"] == "Rory MacDonald & Kirsty Stewart"
    assert edited_entry["division"] == "mixed_doubles"
    assert edited_entry["age_category"] == "40-44"
    assert edited_entry["volunteer_name"] == "Coach Emma"
    assert edited_entry["heat_day_number"] == 2
    assert edited_entry["heat_start_time"] == "09:40"
    assert edited_entry["partner_athlete_id"] is not None

    # Re-syncing from TeamUp should preserve the Race Director's manual Doubles partner, division, slot, and volunteer
    resync_after_edit = client.post(
        f"/api/hyrox/events/{event_id}/sync-teamup",
        json=teamup_v2_payload,
    )
    assert resync_after_edit.status_code == 200
    state_after = client.get(f"/api/hyrox/events/{event_id}/state").get_json()
    rory_after = next(e for e in state_after["entries"] if "Rory MacDonald" in e["display_name"])
    assert rory_after["partner_name"] == "Kirsty Stewart"
    assert rory_after["division"] == "mixed_doubles"
    assert rory_after["volunteer_name"] == "Coach Emma"
    assert rory_after["heat_start_time"] == "09:40"



    # Duplicate delivery with same TEAMUP-WEBHOOK-ID is deduplicated
    wh_dup = client.post(
        f"/api/hyrox/teamup/webhook?event_id={event_id}&secret=cs_secret_99",
        headers={"TEAMUP-WEBHOOK-ID": "tu-wh-uuid-001"},
        json=wh_payload,
    )
    assert wh_dup.status_code == 200
    assert wh_dup.get_json()["deduplicated"] is True

    # Verify Rory's entry was marked DNS by the late_cancelled webhook
    state_after = client.get(f"/api/hyrox/events/{event_id}/state").get_json()
    rory_after = next(e for e in state_after["entries"] if "Rory MacDonald" in e["display_name"])
    assert rory_after["status"] == "dns"

    # 4. Verify SSL CERTIFICATE_VERIFY_FAILED fallback on macOS Python framework builds
    import io
    import ssl
    import urllib.error
    import urllib.request
    from unittest.mock import patch

    calls = []

    class _DummyResp:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return b'{"name": "CS Performance HYROX", "scoped_providers": [{"id": 285151, "name": "CS Performance"}]}'

    def _fake_urlopen(req, timeout=15, context=None):
        calls.append(req.headers.get("Authorization"))
        if len(calls) == 1:
            raise urllib.error.URLError(ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"))
        return _DummyResp()

    with patch.object(urllib.request, "urlopen", side_effect=_fake_urlopen):
        test_resp = client.post("/api/hyrox/teamup/test", json={"api_token": "tu_test_ssl_fallback_token"})
        assert test_resp.status_code == 200
        tdata = test_resp.get_json()
        assert tdata["ok"] is True
        assert tdata["provider_id"] == "285151"
        assert len(calls) == 2

    # 5. Verify PWA manifest & pre-hydrated instant Judge UI
    manifest_resp = client.get("/hyrox/manifest.json")
    assert manifest_resp.status_code == 200
    assert manifest_resp.get_json()["display"] == "standalone"

    judge_resp = client.get(f"/hyrox/judge?entry={rory_after['id']}")
    assert judge_resp.status_code == 200
    judge_html = judge_resp.get_data(as_text=True)
    assert "initialEntryData" in judge_html
    assert "toggleFocusLock" in judge_html
    assert "handleFastTap" in judge_html
    idx_clocks = judge_html.index('class="clocks-grid"')
    idx_btn = judge_html.index('id="primary-action-btn"')
    idx_presc = judge_html.index('id="presc-card"')
    assert idx_clocks < idx_btn < idx_presc
    assert "tap-btn-well" in judge_html
    assert "btn-theme-green" in judge_html

    admin_html = client.get("/hyrox/admin").get_data(as_text=True)
    assert "saveInlineRow" in admin_html
    assert "onInlineDivisionChange" in admin_html
    assert "onModalDivisionChange" in admin_html
    assert "openStartListModal" in admin_html
    assert "downloadStartListPng" in admin_html
    assert "copyStartListWhatsApp" in admin_html
    assert "shareStartListWhatsApp" in admin_html
    assert "toggleStartListCleanMode" in admin_html

    sl_resp = client.get("/hyrox/start-list")
    assert sl_resp.status_code == 200
    assert "start-list-capture-card" in sl_resp.get_data(as_text=True)


def test_weekend_sat28_sun29_four_group_signups_and_setup(client):
    """
    Verify Saturday 28th (14:00-17:00) & Sunday 29th (10:00-14:00) 4-group TeamUp sign-up
    classification, morning class exclusion, and 1:1 staggered slot assignment:
      1. Male Solo (Sat 14:00-15:20)
      2. Male Doubles / Mixed Doubles (Sat 15:30-16:50)
      3. Female Solo (Sun 10:00-11:50)
      4. Female Doubles (Sun 12:00-13:50)
    """
    sample_attendances = [
        # Regular morning classes on Sat 28th & Sun 29th that should be excluded
        {
            "id": 9101,
            "status": "registered",
            "customer": {"id": 801, "first_name": "Early", "last_name": "Riser", "email": "early@example.com"},
            "event": {
                "id": 701,
                "name": "05:30 Thresholds",
                "starts_at": "2026-11-28T05:30:00Z",
                "offering_type": {"name": "05:30 Thresholds"},
            },
        },
        {
            "id": 9102,
            "status": "registered",
            "customer": {"id": 802, "first_name": "Junior", "last_name": "Kid", "email": "kid@example.com"},
            "event": {
                "id": 702,
                "name": "Hyrox Youngstars specific training (age 8-16)",
                "starts_at": "2026-11-28T10:45:00Z",
                "offering_type": {"name": "Hyrox Youngstars specific training (age 8-16)"},
            },
        },
        {
            "id": 9103,
            "status": "registered",
            "customer": {"id": 803, "first_name": "Sunday", "last_name": "Early", "email": "sunearly@example.com"},
            "event": {
                "id": 703,
                "name": "Hyrox Specific Training",
                "starts_at": "2026-11-29T07:00:00Z",
                "offering_type": {"name": "Hyrox Specific Training"},
            },
        },
        # Group 1: Male Solo (Saturday 28th 14:00-17:00)
        {
            "id": 9201,
            "status": "registered",
            "customer": {"id": 811, "first_name": "Callum", "last_name": "Boyd", "email": "callum@example.com", "gender": "M"},
            "event": {
                "id": 711,
                "name": "HYROX Simulation — Male Solo",
                "starts_at": "2026-11-28T14:00:00Z",
                "offering_type": {"name": "HYROX Simulation — Male Solo"},
            },
        },
        # Group 2: Male Doubles & Mixed Doubles (Saturday 28th 14:00-17:00)
        {
            "id": 9202,
            "status": "registered",
            "notes": "Partner: Dan Reid",
            "customer": {"id": 812, "first_name": "Luke", "last_name": "Shaw", "email": "luke@example.com", "gender": "M"},
            "event": {
                "id": 712,
                "name": "HYROX Simulation — Male Pairs",
                "starts_at": "2026-11-28T15:30:00Z",
                "offering_type": {"name": "HYROX Simulation — Male Doubles"},
            },
        },
        {
            "id": 9203,
            "status": "registered",
            "notes": "Partner: Chloe Grant (Mixed Doubles)",
            "customer": {"id": 813, "first_name": "Sam", "last_name": "Kerr", "email": "sam@example.com"},
            "event": {
                "id": 713,
                "name": "HYROX Simulation — Mixed Doubles",
                "starts_at": "2026-11-28T16:00:00Z",
                "offering_type": {"name": "HYROX Simulation — Mixed Doubles"},
            },
        },
        # Group 3: Female Solo (Sunday 29th 10:00-14:00)
        {
            "id": 9204,
            "status": "registered",
            "customer": {"id": 814, "first_name": "Hannah", "last_name": "Millar", "email": "hannah@example.com", "gender": "F"},
            "event": {
                "id": 714,
                "name": "HYROX Simulation — Female Solo",
                "starts_at": "2026-11-29T10:00:00Z",
                "offering_type": {"name": "HYROX Simulation — Female Solo"},
            },
        },
        # Group 4: Female Doubles (Sunday 29th 10:00-14:00)
        {
            "id": 9205,
            "status": "registered",
            "notes": "Partner: Isla Vance",
            "customer": {"id": 815, "first_name": "Megan", "last_name": "Ross", "email": "megan@example.com", "gender": "F"},
            "event": {
                "id": 715,
                "name": "HYROX Simulation — Female Pairs",
                "starts_at": "2026-11-29T12:00:00Z",
                "offering_type": {"name": "HYROX Simulation — Female Pairs"},
            },
        },
    ]

    # 1. Preview sign-ups via POST /api/hyrox/teamup/signups
    prev_res = client.post(
        "/api/hyrox/teamup/signups",
        json={
            "saturday_date": "2026-11-28",
            "sunday_date": "2026-11-29",
            "attendances": sample_attendances,
        },
    )
    assert prev_res.status_code == 200
    prev_data = prev_res.get_json()
    assert prev_data["ok"] is True
    # Only the 5 HYROX weekend entries should be kept (morning non-sim classes excluded)
    assert prev_data["total_signups"] == 5
    groups_by_key = {g["key"]: g for g in prev_data["signup_groups"]}
    assert groups_by_key["male_solo"]["count"] == 1
    assert groups_by_key["male_mixed_doubles"]["count"] == 2
    assert groups_by_key["female_solo"]["count"] == 1
    assert groups_by_key["female_doubles"]["count"] == 1

    # 2. Setup the Saturday 28th & Sunday 29th event + import sign-ups into 1:1 slots
    setup_res = client.post(
        "/api/hyrox/events/setup-weekend",
        json={
            "name": "CS Performance HYROX — Sat 28th & Sun 29th",
            "saturday_date": "2026-11-28",
            "sunday_date": "2026-11-29",
            "interval_mins": 10,
            "force_new": True,
            "attendances": sample_attendances,
        },
    )
    assert setup_res.status_code in (200, 201)
    sdata = setup_res.get_json()
    assert sdata["ok"] is True
    assert sdata["saturday_date"] == "2026-11-28"
    assert sdata["sunday_date"] == "2026-11-29"
    assert sdata["synced_count"] == 5

    entries_by_name = {e["display_name"]: e for e in sdata["entries"]}
    assert entries_by_name["Callum Boyd"]["signup_group"] == "male_solo"
    assert entries_by_name["Callum Boyd"]["heat_day_number"] == 1
    assert entries_by_name["Callum Boyd"]["heat_start_time"] == "14:00"

    assert entries_by_name["Luke Shaw"]["signup_group"] == "male_mixed_doubles"
    assert entries_by_name["Luke Shaw"]["division"] == "men_doubles"
    assert entries_by_name["Luke Shaw"]["heat_day_number"] == 1
    assert entries_by_name["Luke Shaw"]["heat_start_time"] == "15:30"

    assert entries_by_name["Sam Kerr"]["signup_group"] == "male_mixed_doubles"
    assert entries_by_name["Sam Kerr"]["division"] == "mixed_doubles"
    assert entries_by_name["Sam Kerr"]["heat_day_number"] == 1
    assert entries_by_name["Sam Kerr"]["heat_start_time"] == "15:40"

    assert entries_by_name["Hannah Millar"]["signup_group"] == "female_solo"
    assert entries_by_name["Hannah Millar"]["heat_day_number"] == 2
    assert entries_by_name["Hannah Millar"]["heat_start_time"] == "10:00"

    assert entries_by_name["Megan Ross"]["signup_group"] == "female_doubles"
    assert entries_by_name["Megan Ross"]["division"] == "women_doubles"
    assert entries_by_name["Megan Ross"]["heat_day_number"] == 2
    assert entries_by_name["Megan Ross"]["heat_start_time"] == "12:00"


def test_teamup_real_event_names_and_sync_filters_regular_classes(client):
    """
    Verify that `/api/hyrox/events/<id>/sync-teamup` filters out regular gym classes
    ('Hot Strength & Ergs', 'Hyrox Youngstars specific training (age 8-16)', 'Thresholds')
    and accurately sorts CS Fitness's exact TeamUp class names into the 4 groups:
      - Sat 'Hyrox simulation solo' (even with shared offering 'Hyrox simulation solo males ,solo woman pro & female pro double') -> 1. Male Solo
      - Sat 'Hyrox simulation doubles male and mixed doubles' -> 2. Male Doubles / Mixed Doubles
      - Sun 'Hyrox simulations female open solo' & Sun 'Hyrox simulation solo' -> 3. Female Solo
      - Sun 'Hyrox simulations female open doubles' & Sun 'Hyrox simulation doubles' -> 4. Female Doubles
    """
    events = client.get("/api/hyrox/events").get_json()
    event_id = events[0]["id"]

    real_weekend_payload = {
        "results": [
            # Regular Saturday morning classes that previously inflated count to 45 (must be skipped!)
            {
                "id": 9901,
                "status": "registered",
                "customer": {"id": 501, "first_name": "Eilidh", "last_name": "Mcmanus", "gender": "F"},
                "event": {
                    "id": 111112517,
                    "name": "Hot Strength & Ergs",
                    "starts_at": "2026-11-28T09:30:00Z",
                    "offering_type": {"name": "Hot Strength & Ergs"},
                },
            },
            {
                "id": 9902,
                "status": "registered",
                "customer": {"id": 502, "first_name": "Young", "last_name": "Athlete"},
                "event": {
                    "id": 104498152,
                    "name": "Hyrox Youngstars specific training (age 8-16)",
                    "starts_at": "2026-11-28T10:45:00Z",
                },
            },
            # Saturday 14:00 Group 1: Hyrox simulation solo (with misleading shared offering_type name)
            {
                "id": 9903,
                "status": "registered",
                "customer": {"id": 503, "first_name": "Lucas", "last_name": "Kane"},
                "event": {
                    "id": 112225965,
                    "name": "Hyrox simulation solo",
                    "starts_at": "2026-11-28T14:00:00Z",
                    "offering_type": {"name": "Hyrox simulation solo males ,solo woman pro & female pro double"},
                },
            },
            # Saturday 14:00 Group 2: Hyrox simulation doubles male and mixed doubles
            {
                "id": 9904,
                "status": "registered",
                "customer": {"id": 501, "first_name": "Eilidh", "last_name": "Mcmanus", "gender": "F"},
                "event": {
                    "id": 112228753,
                    "name": "Hyrox simulation doubles male and mixed doubles",
                    "starts_at": "2026-11-28T14:00:00Z",
                    "offering_type": {"name": "Hyrox simulation doubles male and mixed doubles"},
                },
            },
            {
                "id": 9905,
                "status": "registered",
                "customer": {"id": 504, "first_name": "Ewan", "last_name": "Stewart", "gender": "M"},
                "event": {
                    "id": 112228753,
                    "name": "Hyrox simulation doubles male and mixed doubles",
                    "starts_at": "2026-11-28T14:00:00Z",
                    "offering_type": {"name": "Hyrox simulation doubles male and mixed doubles"},
                },
            },
            # Sunday 10:00 Group 3: Hyrox simulations female open solo + Sunday Hyrox simulation solo
            {
                "id": 9906,
                "status": "registered",
                "customer": {"id": 505, "first_name": "Eve", "last_name": "Cunningham", "gender": "F"},
                "event": {
                    "id": 112228742,
                    "name": "Hyrox simulations female open solo",
                    "starts_at": "2026-11-29T10:00:00Z",
                    "offering_type": {"name": "Hyrox simulations female open solo"},
                },
            },
            {
                "id": 9907,
                "status": "registered",
                "customer": {"id": 506, "first_name": "Ava", "last_name": "Stewart"},
                "event": {
                    "id": 112226190,
                    "name": "Hyrox simulation solo",
                    "starts_at": "2026-11-29T10:00:00Z",
                    "offering_type": {"name": "Hyrox simulation solo males ,solo woman pro & female pro double"},
                },
            },
            # Sunday 10:00 Group 4: Hyrox simulations female open doubles + Sunday Hyrox simulation doubles
            {
                "id": 9908,
                "status": "registered",
                "customer": {"id": 507, "first_name": "Claire", "last_name": "Robertson"},
                "event": {
                    "id": 112228735,
                    "name": "Hyrox simulations female open doubles",
                    "starts_at": "2026-11-29T10:00:00Z",
                    "offering_type": {"name": "Hyrox simulations female open doubles"},
                },
            },
        ]
    }

    sync_res = client.post(f"/api/hyrox/events/{event_id}/sync-teamup", json=real_weekend_payload)
    assert sync_res.status_code == 200
    sync_json = sync_res.get_json()
    assert sync_json["synced_count"] == 6
    assert sync_json["skipped_count"] == 2

    groups = {g["key"]: g for g in sync_json["signup_groups"]}
    assert groups["male_solo"]["count"] == 1
    assert groups["male_solo"]["entries"][0]["display_name"] == "Lucas Kane"
    assert groups["male_solo"]["entries"][0]["teamup_event_name"] == "Hyrox simulation solo"

    assert groups["male_mixed_doubles"]["count"] == 2
    dbl_by_name = {e["display_name"]: e for e in groups["male_mixed_doubles"]["entries"]}
    assert dbl_by_name["Eilidh Mcmanus"]["division"] == "mixed_doubles"
    assert dbl_by_name["Eilidh Mcmanus"]["partner_name"] == "Jax Stevenson"
    assert dbl_by_name["Ewan Stewart"]["division"] == "men_doubles"
    assert dbl_by_name["Ewan Stewart"]["partner_name"] == "Ewan Taylor"

    assert groups["female_solo"]["count"] == 2
    fsolo_names = {e["display_name"] for e in groups["female_solo"]["entries"]}
    assert fsolo_names == {"Eve Cunningham", "Ava Stewart"}

    assert groups["female_doubles"]["count"] == 1
    assert groups["female_doubles"]["entries"][0]["display_name"] == "Claire Robertson"
    assert groups["female_doubles"]["entries"][0]["division"] == "women_doubles"


def test_confirmed_13_road_to_glasgow_signups_enrichment(client):
    """
    Verify all 13 confirmed Saturday 28th & Sunday 29th HYROX Sim sign-ups
    cross-referenced with Road to Glasgow are enriched with the exact partners,
    divisions, and 4-group assignments.
    """
    events_res = client.get("/api/hyrox/events").get_json()
    event_id = events_res[0]["id"]

    apply_res = client.post(f"/api/hyrox/events/{event_id}/apply-road-to-glasgow")
    assert apply_res.status_code == 200
    apply_json = apply_res.get_json()
    assert apply_json["ok"] is True
    assert apply_json["seeded_count"] == 13

    entries = apply_json["entries"]
    assert len(entries) == 13
    by_name = {e["display_name"]: e for e in entries}

    # 1-3: Group 1 — Male Solo Open (Saturday 28th)
    for solo_male in ("Lucas Kane", "Ross Martin", "Scott Firth"):
        assert by_name[solo_male]["division"] == "men_open"
        assert by_name[solo_male]["partner_name"] == ""
        assert by_name[solo_male]["signup_group"] == "male_solo"

    # 4-9: Group 2 — Male Doubles / Mixed Doubles (Saturday 28th)
    assert by_name["Eilidh Mcmanus"]["division"] == "mixed_doubles"
    assert by_name["Eilidh Mcmanus"]["partner_name"] == "Jax Stevenson"
    assert by_name["Eilidh Mcmanus"]["signup_group"] == "male_mixed_doubles"

    assert by_name["Ewan Stewart"]["division"] == "men_doubles"
    assert by_name["Ewan Stewart"]["partner_name"] == "Ewan Taylor"
    assert by_name["Ewan Stewart"]["signup_group"] == "male_mixed_doubles"

    assert by_name["Keiran Jackson"]["division"] == "men_doubles"
    assert by_name["Keiran Jackson"]["partner_name"] == "Ricky Simpson"
    assert by_name["Keiran Jackson"]["signup_group"] == "male_mixed_doubles"

    assert by_name["Scott McDonald"]["division"] == "men_doubles"
    assert by_name["Scott McDonald"]["partner_name"] == "Liam Blair"
    assert by_name["Scott McDonald"]["signup_group"] == "male_mixed_doubles"

    assert by_name["Steven Rosie"]["division"] == "mixed_doubles"
    assert by_name["Steven Rosie"]["partner_name"] == "Fiona Sharp"
    assert by_name["Steven Rosie"]["signup_group"] == "male_mixed_doubles"

    assert by_name["Joe Wardle"]["division"] == "men_open"
    assert by_name["Joe Wardle"]["partner_name"] == ""
    assert by_name["Joe Wardle"]["notes"] == ""
    assert by_name["Joe Wardle"]["signup_group"] == "male_solo"

    # Verify editing an entry (e.g. changing Doubles -> Solo and changing time slot) persists across requests without reverting
    state_before = client.get(f"/api/hyrox/events/{event_id}/state").get_json()
    heats = state_before["heats"]
    target_heat = next(h for h in heats if h["start_time"] == "14:25" and int(h.get("day_number") or 1) == 1)
    keiran = by_name["Keiran Jackson"]
    edit_res = client.put(
        f"/api/hyrox/entries/{keiran['id']}",
        json={
            "division": "men_open",
            "display_name": "Keiran Jackson & Ricky Simpson",
            "heat_id": target_heat["id"],
            "volunteer_name": "Coach Sarah",
        },
    )
    assert edit_res.status_code == 200
    edited = edit_res.get_json()
    assert edited["division"] == "men_open"
    assert edited["partner_name"] == ""
    assert edited["full_display_name"] == "Keiran Jackson"
    assert edited["heat_id"] == target_heat["id"]
    assert edited["heat_start_time"] == "14:25"

    # Subsequent splits save + state fetch must NOT revert division, partner_name, or heat_id
    splits_res = client.put(
        f"/api/hyrox/entries/{keiran['id']}/splits",
        json={"splits": [], "status": "scheduled", "penalty_str": "00:00", "wall_ball_reps": 0},
    )
    assert splits_res.status_code == 200
    state_after = client.get(f"/api/hyrox/events/{event_id}/state").get_json()
    keiran_after = next(e for e in state_after["entries"] if e["id"] == keiran["id"])
    assert keiran_after["division"] == "men_open"
    assert keiran_after["partner_name"] == ""
    assert keiran_after["full_display_name"] == "Keiran Jackson"
    assert keiran_after["heat_id"] == target_heat["id"]
    assert keiran_after["heat_start_time"] == "14:25"

    # 10-13: Group 3 — Female Solo Open (Sunday 29th)
    for solo_female in ("Eve Cunningham", "Joanne Campbell", "Lesley Anne Cooper", "Ava Stewart"):
        assert by_name[solo_female]["division"] == "women_open"
        assert by_name[solo_female]["partner_name"] == ""
        assert by_name[solo_female]["notes"] == ""
        assert by_name[solo_female]["signup_group"] == "female_solo"






