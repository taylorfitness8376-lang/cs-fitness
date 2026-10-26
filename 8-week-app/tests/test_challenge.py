import json
from database import calculate_challenge_targets


def test_chris_excel_formulas_for_ewan():
    calc = calculate_challenge_targets(
        start_weight_kg=84.0,
        target_weight_kg=78.3,
        start_body_fat_pct=16.0,
        target_body_fat_pct=14.0,
        protein_g=150,
        start_date="2026-10-19",
        goal="Weight Loss",
        returning_member=False,
    )
    assert calc["fat_mass_kg"] == 13.44
    assert calc["lean_body_mass_kg"] == 70.56
    assert calc["to_lose_kg"] == -5.7
    assert calc["target_calories"] == 2173
    assert calc["target_protein_g"] == 150
    assert calc["target_fats_g"] == 72
    assert calc["target_carbs_g"] == 230
    assert calc["target_water_l"] == 3.66
    assert calc["end_date"] == "2026-12-14"

    wt = calc["weekly_targets"]
    assert len(wt) == 8
    expected_weights = [84.00, 83.16, 82.33, 81.51, 80.69, 79.88, 79.08, 78.29]
    expected_steps = [10000, 11000, 12000, 13000, 14000, 15000, 16000, 17000]
    for i in range(8):
        assert wt[i]["target_weight_kg"] == expected_weights[i]
        assert wt[i]["min_steps"] == expected_steps[i]


def test_returning_member_step_targets():
    calc = calculate_challenge_targets(start_weight_kg=68.0, target_weight_kg=62.5, returning_member=True)
    steps = [w["min_steps"] for w in calc["weekly_targets"]]
    assert steps[:5] == [14000, 14000, 14000, 14000, 14000]
    assert steps[5:] == [15000, 16000, 17000]


def test_challenge_page_and_overview(client):
    res = client.get("/challenge")
    assert res.status_code == 200
    assert b"CS FITNESS" in res.data

    ov = client.get("/api/challenge/overview?date=2026-10-17").get_json()
    assert ov["profile"]["client_name"] == "Ewan t"
    assert ov["profile"]["target_calories"] == 2173
    assert ov["checkin"]["steps"] == 0
    assert len(ov["staple_meals"]) >= 10
    assert len(ov["step_routes"]) >= 5
    assert "#Ewan" in ov["whatsapp_share"]["caption"]


def test_checkin_quick_actions_and_class_mapping(client):
    # Log morning weight & water +500ml on Week 1 Day 1
    res = client.post("/api/challenge/checkins", json={
        "date": "2026-10-19",
        "weight_kg": 83.8,
        "steps": 6200,
        "water_add_l": 0.5,
        "cs_class": "mwf-6am-cardio",
    })
    assert res.status_code == 200
    c = res.get_json()["checkin"]
    assert c["weight_kg"] == 83.8
    assert c["water_l"] == 0.5
    assert c["training_type"] == "CARDIO"

    # Add a strength session on the same day -> auto-upgrades to GYM & CARDIO
    res2 = client.post("/api/challenge/checkins", json={
        "date": "2026-10-19",
        "cs_class": "tt-6am-strength",
        "add_staple_id": 1,
    })
    c2 = res2.get_json()["checkin"]
    assert c2["training_type"] == "GYM & CARDIO"
    assert c2["protein_g"] >= 35


def test_workouts_and_logging(client):
    w_res = client.get("/api/challenge/workouts?track=mens").get_json()
    assert len(w_res["workouts"]) == 4
    assert w_res["workouts"][0]["title"] == "WORKOUT 1 - FULL BODY"

    log_res = client.post("/api/challenge/workouts/log", json={
        "track": "mens",
        "workout_num": 1,
        "week_num": 2,
        "row_key": "W1_A_1",
        "exercise_order": "A",
        "exercise_name": "Barbell Back Squat",
        "target_sets": 1,
        "target_reps": "8",
        "weight_reps": "75kg x8",
        "logged_date": "2026-10-26",
        "mark_checkin_gym": True,
    })
    assert log_res.status_code == 200
    assert log_res.get_json()["weight_reps"] == "75kg x8"


def test_garmin_and_mfp_sync_endpoints(client):
    sim = client.post("/api/challenge/sync/simulate", json={"date": "2026-10-20"}).get_json()
    assert sim["ok"] is True
    assert sim["checkin"]["steps"] >= 10000
    assert sim["checkin"]["protein_g"] >= 150

    wh = client.post("/api/challenge/sync/webhook", json={
        "date": "2026-10-21",
        "steps": 13450,
        "weight_kg": 83.5,
        "sleep_mins": 495,
        "activities": [{"activityType": "strength_training", "activityName": "Men's Workout 2"}],
        "calories": 2160,
        "protein_g": 156,
        "water_ml": 3700,
    }).get_json()
    assert wh["ok"] is True
    assert wh["checkin"]["steps"] == 13450
    assert wh["checkin"]["training_type"] == "GYM"
    assert wh["checkin"]["water_l"] == 3.7


def test_telegram_and_whatsapp_integrations(client):
    # Inbound Telegram Bot commands
    r_wt = client.post("/api/challenge/telegram/webhook", json={"command": "/weight 83.2", "date": "2026-10-22"}).get_json()
    assert r_wt["checkin"]["weight_kg"] == 83.2

    r_st = client.post("/api/challenge/telegram/webhook", json={"command": "/steps 12400", "date": "2026-10-22"}).get_json()
    assert r_st["checkin"]["steps"] == 12400

    # Outbound Telegram weekly summary
    tg = client.post("/api/challenge/telegram/send", json={"week_num": 0}).get_json()
    assert tg["ok"] is True
    assert "t.me/" in tg["deep_link_url"]
    assert "WEEKLY AVERAGES" in tg["message"]

    # WhatsApp export importer
    sample_chat = (
        "[16/10/2026, 10:04:49] L: Classes at CS Fitness green heart Mon/Wed/Fri 6am Cardio and Tue/Thu Strength!\n"
        "[17/10/2026, 20:15:00] ~ Ewan: 11,450 steps banked and steak burger fakeaway done! #Ewan #steps #dinner #macros\n"
    )
    imp = client.post("/api/challenge/whatsapp/import", json={"chat_text": sample_chat}).get_json()
    assert imp["extracted_count"] == 2
    assert len(imp["coach_announcements"]) == 1
    assert imp["member_posts"][0]["steps_extracted"] == 11450


def test_daily_activities_manual_and_garmin_runs(client):
    # Log manual gym class on Tomorrow (2026-10-18)
    r1 = client.post("/api/challenge/activities", json={
        "date": "2026-10-18",
        "source": "Strength Logger",
        "category": "GYM",
        "title": "Men's Workout 1 - Full Body",
        "duration_mins": 50,
    }).get_json()
    assert r1["ok"] is True

    # Log Garmin 5k run on the same day -> auto-calculates pace & upgrades training_type to GYM & CARDIO
    r2 = client.post("/api/challenge/activities", json={
        "date": "2026-10-18",
        "source": "Garmin Connect",
        "activity_type": "running",
        "category": "CARDIO",
        "title": "Garmin Helix 5k Run",
        "distance_km": 5.0,
        "duration_mins": 26.0,
        "avg_hr": 154,
        "calories": 390,
        "steps": 4800,
    }).get_json()
    assert r2["checkin"]["training_type"] == "GYM & CARDIO"
    assert "5.0km @ 5:12 /km" in r2["checkin"]["class_attended"]


def test_progress_summary_workout_rollup_photos_and_sync(client):
    # 1. Log a workout set in Week 1 and roll it up to Today + Check-In Sheet + Week-over-Week
    client.post("/api/challenge/workouts/log", json={
        "track": "mens",
        "workout_num": 1,
        "week_num": 1,
        "row_key": "W1_A_1",
        "exercise_order": "A",
        "exercise_name": "Barbell Back Squat",
        "target_sets": 4,
        "target_reps": "6",
        "weight_reps": "80kg x6, 6, 6, 6",
        "logged_date": "2026-10-19",
    })
    rollup = client.post("/api/challenge/workouts/rollup", json={
        "track": "mens",
        "workout_num": 1,
        "week_num": 1,
        "date": "2026-10-19",
    }).get_json()
    assert rollup["ok"] is True
    assert rollup["rolled_up"] is True
    assert rollup["sets"] == 4
    assert rollup["volume_kg"] == 1920

    # 2. Upload all 3 weekly poses (Front, Side, Back) for Week 1
    for pose in ("Front", "Side", "Back"):
        p_res = client.post("/api/challenge/photos/upload", json={
            "week_num": 1,
            "pose": pose,
            "taken_date": "2026-10-19",
            "weight_kg": 83.6,
            "photo_data_url": "data:image/jpeg;base64,abc123",
        }).get_json()
        assert p_res["ok"] is True

    # 3. Verify Week-over-Week progress summary includes the workout volume & 3/3 photos
    prog = client.get("/api/challenge/progress/summary?week=1").get_json()
    assert prog["ok"] is True
    wk1 = [w for w in prog["weeks"] if w["week_num"] == 1][0]
    assert wk1["workout_sets_logged"] == 4
    assert wk1["workout_volume_kg"] == 1920
    assert wk1["photos_count"] == 3
    assert set(wk1["poses_logged"]) == {"Front", "Side", "Back"}

    # 4. Save Garmin & MyFitnessPal account details and import a CSV export
    conn = client.post("/api/challenge/sync/connect", json={
        "date": "2026-10-19",
        "garmin_email": "ewan@example.com",
        "mfp_username": "ewan_mfp",
    }).get_json()
    assert conn["ok"] is True
    assert conn["integrations"]["garmin_email"] == "ewan@example.com"
    assert conn["integrations"]["mfp_username"] == "ewan_mfp"

    csv_imp = client.post("/api/challenge/sync/import-data", json={
        "source": "mfp",
        "date": "2026-10-19",
        "content": "Date,Calories,Protein (g),Carbohydrates (g),Fat (g),Fiber\n2026-10-19,2150,158,220,70,32\n",
    }).get_json()
    assert csv_imp["ok"] is True
    assert csv_imp["imported_count"] == 1


def test_in_app_weekly_checkin_submit_and_coach_review(client):
    sub = client.post("/api/challenge/weekly-checkin/submit", json={
        "week_num": 1,
        "challenger_comments": "Hit all step targets, squat felt strong, energy high.",
    }).get_json()
    assert sub["ok"] is True
    assert sub["status"] == "Submitted"

    rev = client.post("/api/challenge/weekly-checkin/review", json={
        "week_num": 1,
        "coach_feedback": "Awesome Week 1 Ewan! Keep calories at 2173 and steps moving to 11k.",
        "new_target_calories": 2173,
        "new_target_protein_g": 155,
    }).get_json()
    assert rev["ok"] is True
    assert rev["status"] == "Reviewed"

    prog = client.get("/api/challenge/progress/summary").get_json()
    wk1 = [w for w in prog["weeks"] if w["week_num"] == 1][0]
    assert wk1["submission_status"] == "Reviewed"
    assert "Hit all step targets" in wk1["challenger_comments"]
    assert "Awesome Week 1 Ewan!" in wk1["coach_feedback"]


def test_garmin_oauth1_signature_and_client(tmp_path):
    from sync_service import _oauth1_auth_header, _BuiltinGarminClient
    hdr = _oauth1_auth_header(
        "GET",
        "https://connectapi.garmin.com/oauth-service/oauth/preauthorized",
        {"ticket": "ST-12345", "login-url": "https://sso.garmin.com/sso/embed"},
        "ck_test",
        "cs_test",
    )
    assert hdr.startswith("OAuth ")
    assert 'oauth_consumer_key="ck_test"' in hdr
    assert 'oauth_signature="' in hdr
    gc = _BuiltinGarminClient(email="ewan@example.com", password="secret", cookie_path=str(tmp_path / "garmin.json"))
    assert gc.session.headers.get("DI-Backend") == "connectapi.garmin.com"


def test_cohort_blocks_enroll_rollover_and_auth(client):
    # 1. List 5 annual 8-week cohort blocks
    blocks_res = client.get("/api/challenge/blocks").get_json()
    assert blocks_res["ok"] is True
    assert len(blocks_res["blocks"]) >= 5
    active_block = [b for b in blocks_res["blocks"] if b["status"] == "Active"][0]
    upcoming_block = [b for b in blocks_res["blocks"] if b["status"] == "Upcoming"][0]
    assert active_block["invite_code"] == "CS-OCT2026"

    # 2. Create a new 8-week block
    new_blk = client.post("/api/challenge/blocks", json={
        "name": "Block 4 · Late Summer 2027",
        "start_date": "2027-08-16",
        "invite_code": "CS-AUG2027",
        "gap_weeks_after": 2,
    }).get_json()
    assert new_blk["ok"] is True
    assert new_blk["block"]["end_date"] == "2027-10-11"
    assert new_blk["block"]["pre_coaching_date"] == "2027-08-09"

    # 3. Payment / Signup form webhook enrolls a new challenger into the active block
    enroll_res = client.post("/api/challenge/blocks/webhook/enroll", json={
        "invite_code": active_block["invite_code"],
        "client_name": "James Miller",
        "email": "james@example.com",
        "start_weight_kg": 92.0,
        "target_weight_kg": 85.0,
        "start_body_fat_pct": 20.0,
        "protein_g": 170,
        "payment_reference": "stripe_pi_998877",
    }).get_json()
    assert enroll_res["ok"] is True
    assert enroll_res["block"]["invite_code"] == "CS-OCT2026"
    james_pid = enroll_res["profile_id"]

    # 4. Sign in with James's email (sets password on first login)
    login_res = client.post("/api/challenge/auth/login", json={
        "email": "james@example.com",
    }).get_json()
    assert login_res["ok"] is True
    assert login_res["profile_id"] == james_pid

    # 5. Rollover active block members to the next sequential 8-week block (sets returning = 1 -> 14k steps)
    roll_res = client.post("/api/challenge/blocks/rollover", json={
        "from_block_id": active_block["id"],
        "to_block_id": upcoming_block["id"],
    }).get_json()
    assert roll_res["ok"] is True
    assert roll_res["rolled_over_count"] >= 2






