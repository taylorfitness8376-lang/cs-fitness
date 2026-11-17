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
    assert state["splits_template"][0]["label"].startswith("Run 1")
    assert state["splits_template"][15]["station_key"] == "wall_balls"

    ewan = next(e for e in state["entries"] if "Ewan Taylor" in e["display_name"])
    assert ewan["run_distance_km"] == 1.2
    assert ewan["total_run_distance_km"] == 9.6
    assert ewan["avg_run_kph"] > 0
    assert "kph" in ewan["avg_run_kph_formatted"]
    run1_split = ewan["splits"][0]
    assert run1_split["distance_km"] == 1.2
    assert run1_split["pace_kph"] > 0
    assert "kph" in run1_split["pace_kph_formatted"]

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

    # Verify Roxfit labels, PB detection, and split ranks on Ewan Taylor
    assert ewan["avg_run_rank"] >= 1
    assert ewan["splits"][1]["roxfit_label"] == "Ski"
    assert any(s.get("is_pb") for s in ewan["splits"])
    assert all(s.get("split_rank") is not None for s in ewan["splits"])


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
    assert b"/static/logo.jpg" in root_hyrox_resp.data

    admin_resp = client.get("/hyrox/admin")
    assert admin_resp.status_code == 200
    assert b"TEAMUP CSV IMPORT" in admin_resp.data
    assert b'id="modal-division"' in admin_resp.data
    assert b'<option value="men_doubles">Men&#39;s Open Doubles (M Open Dbl)</option>' in admin_resp.data
    assert b'<option value="mixed_doubles">Mixed Doubles (Mixed Dbl)</option>' in admin_resp.data
    assert b'<option value="women_pro_doubles">Female Pro Doubles (F Pro Dbl)</option>' in admin_resp.data

    # Surface 2: Volunteer Judge App (Direct Athlete Selector + Top Run Pace Strip)
    judge_resp = client.get(f"/hyrox/judge?entry={ewan['id']}")
    assert judge_resp.status_code == 200
    assert b"Wall Ball Rep Counter" in judge_resp.data
    assert b"Avg Run Pace" in judge_resp.data
    assert b"/static/logo.jpg" in judge_resp.data

    # Surface 3: Live Gym TV Broadcast (HYROX App / Roxfit 16-split view)
    tv_resp = client.get("/hyrox/tv")
    assert tv_resp.status_code == 200
    assert b"HYROX APP VIEW" in tv_resp.data
    assert b"/static/logo.jpg" in tv_resp.data

    # Surface 4: Athlete Results & Social Finisher Card
    res_resp = client.get(f"/hyrox/results/{ewan['id']}")
    assert res_resp.status_code == 200
    assert b"FINISHER CARD GENERATOR" in res_resp.data
    assert b"/static/logo.jpg" in res_resp.data

    ath_resp = client.get(f"/hyrox/athlete/{ewan['athlete_id']}")
    assert ath_resp.status_code == 200
    assert b"Ewan Taylor" in ath_resp.data


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
    # Verify layout order: clocks -> primary tap button -> prescription/next event box -> average run pace strip
    idx_clocks = judge_html.index('class="clocks-grid"')
    idx_btn = judge_html.index('id="primary-action-btn"')
    idx_presc = judge_html.index('id="presc-card"')
    idx_telemetry = judge_html.index('id="run-telemetry-strip"')
    assert idx_clocks < idx_btn < idx_presc < idx_telemetry




