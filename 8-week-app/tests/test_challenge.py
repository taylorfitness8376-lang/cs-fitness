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

    # 5. Non-admin challenger cannot roll over an entire block; Admin (Ewan) performs the block rollover
    non_admin_roll = client.post("/api/challenge/blocks/rollover", json={
        "from_block_id": active_block["id"],
        "to_block_id": upcoming_block["id"],
    })
    assert non_admin_roll.status_code == 403

    client.post("/api/challenge/auth/login", json={"email": "taylor.ewan@gmail.com"})
    roll_res = client.post("/api/challenge/blocks/rollover", json={
        "from_block_id": active_block["id"],
        "to_block_id": upcoming_block["id"],
    }).get_json()
    assert roll_res["ok"] is True
    assert roll_res["rolled_over_count"] >= 2


def test_coach_admin_portal_and_three_admins(client):
    # 1. Challenger page no longer shows TV CMS link and shows 4. Settings & Sync
    ch_page = client.get("/challenge")
    assert ch_page.status_code == 200
    html = ch_page.get_data(as_text=True)
    assert "4. Settings &amp; Sync" in html
    assert ">TV CMS<" not in html

    # 2. Dedicated Coach & Admin Portal renders cleanly
    adm_page = client.get("/challenge/admin")
    assert adm_page.status_code == 200
    assert "COACH &amp; ADMIN PORTAL" in adm_page.get_data(as_text=True)

    # 3. 3 Admins (Chris, Laura, Ewan) are configured
    admins_res = client.get("/api/challenge/admin/admins").get_json()
    assert admins_res["ok"] is True
    names = {a["client_name"].lower() for a in admins_res["admins"]}
    assert {"ewan t", "chris", "laura"}.issubset(names)

    # 4. Update Chris's admin email address
    chris_row = [a for a in admins_res["admins"] if a["client_name"].lower() == "chris"][0]
    upd = client.post("/api/challenge/admin/update-admin-account", json={
        "profile_id": chris_row["profile_id"],
        "email": "chris.coach@taylorfitness.co.uk",
        "role": "admin",
    }).get_json()
    assert upd["ok"] is True
    assert upd["admin"]["email"] == "chris.coach@taylorfitness.co.uk"

    # 5. Challenger deep-dive endpoint returns weekly sheet, trajectory & photos for comparison
    det = client.get("/api/challenge/admin/challenger-detail?profile_id=1&week=1").get_json()
    assert det["ok"] is True
    assert det["profile"]["client_name"] == "Ewan t"
    assert len(det["week_over_week"]) == 9
    assert len(det["week_sheet"]["days"]) == 7

    # 6. 100-challenger summary roster endpoint returns KPIs and summary rows
    ros = client.get("/api/challenge/admin/cohort-summary?week=1").get_json()
    assert ros["ok"] is True
    assert ros["kpis"]["total_challengers"] >= 1
    assert any(r["client_name"] == "Ewan t" for r in ros["roster"])


def test_monday_start_friday_checkin_and_workout_delete(client):
    # 1. Verify Check-In Schedule:
    #    - Week 0 = Day 1 Monday Start (photos_required=True)
    #    - Week 1 = First Friday Check-In (photos_required=False)
    #    - Week 2..8 = Friday Check-Ins (photos_required=True)
    wk0 = client.get("/api/challenge/week/0").get_json()
    assert wk0["checkin_day"] == "Monday (Day 1 Start)"
    assert wk0["photos_required"] is True

    wk1 = client.get("/api/challenge/week/1").get_json()
    assert wk1["checkin_day"] == "Friday"
    assert wk1["checkin_date"] == "2026-10-23"
    assert wk1["photos_required"] is False

    wk2 = client.get("/api/challenge/week/2").get_json()
    assert wk2["checkin_day"] == "Friday"
    assert wk2["checkin_date"] == "2026-10-30"
    assert wk2["photos_required"] is True

    # 2. Add a manual gym workout and a Garmin-synced run on the same day, then delete both
    d = "2026-10-22"
    add_gym = client.post("/api/challenge/activities", json={
        "date": d,
        "activity_type": "strength",
        "category": "GYM",
        "title": "Men's Club",
        "duration_mins": 45,
        "calories": 380,
    }).get_json()
    assert add_gym["ok"] is True
    assert add_gym["checkin"]["training_type"] == "GYM"
    gym_act_id = add_gym["daily_activities"][0]["id"]

    # Simulate a Garmin-synced run activity
    garmin_webhook = client.post("/api/challenge/sync/garmin", json={
        "date": d,
        "steps": 12400,
        "activities": [
            {
                "activityId": "garmin_run_999",
                "activityName": "Morning 5k Run",
                "activityType": "running",
                "durationInSeconds": 1500,
                "distanceInMeters": 5000,
                "ActiveKilocalories": 340,
            }
        ],
    }).get_json()
    assert garmin_webhook["ok"] is True
    ov = client.get(f"/api/challenge/overview?date={d}").get_json()
    assert ov["checkin"]["training_type"] == "GYM & CARDIO"
    assert len(ov["daily_activities"]) == 2
    run_act = [a for a in ov["daily_activities"] if a["garmin_activity_id"] == "garmin_run_999"][0]

    # Delete the Garmin-synced run
    del_run = client.delete(f"/api/challenge/activities/{run_act['id']}").get_json()
    assert del_run["ok"] is True
    assert del_run["training_type"] == "GYM"
    assert len(del_run["daily_activities"]) == 1

    # Re-syncing the same Garmin run should NOT re-import it because it was deleted (tombstoned)
    client.post("/api/challenge/sync/garmin", json={
        "date": d,
        "steps": 12500,
        "activities": [
            {
                "activityId": "garmin_run_999",
                "activityName": "Morning 5k Run",
                "activityType": "running",
                "durationInSeconds": 1500,
                "distanceInMeters": 5000,
            }
        ],
    })
    ov_after_resync = client.get(f"/api/challenge/overview?date={d}").get_json()
    assert len(ov_after_resync["daily_activities"]) == 1

    # Delete the remaining manual gym workout -> training_type resets to REST
    del_gym = client.delete(f"/api/challenge/activities/{gym_act_id}").get_json()
    assert del_gym["ok"] is True
    assert del_gym["training_type"] == "REST"
    assert len(del_gym["daily_activities"]) == 0


def test_multi_user_data_isolation_for_alan_vs_ewan(client):
    """Challengers signing up via invite (e.g. Alan) must NEVER see Ewan's data, photos, Garmin config, or admin endpoints."""
    # 1. Seed Ewan's data (profile_id=1) with a check-in, photo, Garmin email, and weekly submission
    client.post("/api/challenge/checkin", json={
        "date": "2026-10-19",
        "weight_kg": 84.0,
        "steps": 14200,
        "calories": 2150,
        "protein_g": 155,
    })
    client.post("/api/challenge/photos/upload", json={
        "week_num": 0,
        "pose": "Front",
        "taken_date": "2026-10-19",
        "weight_kg": 84.0,
        "photo_data_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    })
    client.post("/api/challenge/integrations", json={
        "garmin_email": "taylor.ewan@gmail.com",
        "mfp_username": "ewantaylor",
    })
    client.post("/api/challenge/weekly-checkin/submit", json={
        "week_num": 1,
        "challenger_comments": "Ewan private week 1 notes",
    })

    # 2. Unauthenticated visitor with challenge_force_unauthed is redirected to /challenge/login
    with client.session_transaction() as sess:
        sess.clear()
        sess["challenge_force_unauthed"] = True
    unauth_resp = client.get("/challenge")
    assert unauth_resp.status_code in (301, 302)
    assert "/challenge/login" in unauth_resp.headers["Location"]

    # 3. Attempting to hijack Ewan's admin account via public /api/challenge/blocks/join is blocked (403)
    hijack_resp = client.post("/api/challenge/blocks/join", json={
        "invite_code": "CS-OCT2026",
        "client_name": "Ewan t",
        "email": "taylor.ewan@gmail.com",
    })
    assert hijack_resp.status_code == 403

    # 4. Alan signs up via the invite code CS-OCT2026
    join_resp = client.post("/api/challenge/blocks/join", json={
        "invite_code": "CS-OCT2026",
        "client_name": "Alan",
        "email": "alan@example.com",
        "password": "alanpassword",
        "start_weight_kg": 90.0,
        "target_weight_kg": 83.0,
        "start_body_fat_pct": 20.0,
        "protein_g": 160,
    })
    assert join_resp.status_code == 200
    join_data = join_resp.get_json()
    assert join_data["ok"] is True
    alan_pid = join_data["profile_id"]
    assert alan_pid != 1

    # 5. Alan fetches /api/challenge/overview -> sees ONLY Alan's empty data, 0 of Ewan's photos, and blank Garmin email
    alan_ov = client.get("/api/challenge/overview?date=2026-10-19").get_json()
    assert alan_ov["profile"]["id"] == alan_pid
    assert alan_ov["profile"]["client_name"] == "Alan"
    assert alan_ov["checkin"]["steps"] == 0
    assert alan_ov["checkin"]["weight_kg"] is None
    assert len(alan_ov["progress_photos"]) == 0
    assert alan_ov["integrations"]["garmin_email"] == ""
    assert alan_ov["integrations"]["mfp_username"] == ""

    # 6. Even if Alan passes ?profile_id=1 on API endpoints, server ignores it and keeps Alan isolated
    spoof_ov = client.get("/api/challenge/overview?date=2026-10-19&profile_id=1").get_json()
    assert spoof_ov["profile"]["id"] == alan_pid
    assert len(spoof_ov["progress_photos"]) == 0

    spoof_photos = client.get("/api/challenge/photos?profile_id=1").get_json()
    assert len(spoof_photos) == 0

    alan_prog = client.get("/api/challenge/progress/summary?profile_id=1").get_json()
    assert alan_prog["profile"]["id"] == alan_pid
    assert len(alan_prog["all_profiles"]) == 1
    assert alan_prog["all_profiles"][0]["id"] == alan_pid
    assert len(alan_prog["weekly_submissions"]) == 0

    # 7. Alan cannot switch user to Ewan (403) or access Coach Admin endpoints (403)
    sw_resp = client.post("/api/challenge/auth/switch-user", json={"profile_id": 1})
    assert sw_resp.status_code in (401, 403)

    assert client.get("/api/challenge/coach/cohort").status_code == 403
    assert client.get("/api/challenge/admin/cohort-summary").status_code == 403
    assert client.get("/api/challenge/admin/challenger-detail?profile_id=1").status_code == 403
    assert client.get("/api/challenge/admin/admins").status_code == 403
    admin_page_resp = client.get("/challenge/admin")
    assert admin_page_resp.status_code in (301, 302)

    # 8. Alan's /api/challenge/blocks only lists Alan, never Ewan or other challengers
    alan_blocks = client.get("/api/challenge/blocks").get_json()
    assert len(alan_blocks["users"]) == 1
    assert alan_blocks["users"][0]["profile_id"] == alan_pid

    # 9. Admin (Ewan) signs in and CAN access Admin endpoints and view both Ewan & Alan
    login_ewan = client.post("/api/challenge/auth/login", json={
        "email": "taylor.ewan@gmail.com",
        "password": "ewanadminpassword",
    }).get_json()
    assert login_ewan["ok"] is True
    assert login_ewan["role"] == "admin"

    cohort_sum = client.get("/api/challenge/admin/cohort-summary?week=1").get_json()
    assert cohort_sum["ok"] is True
    names = [r["client_name"] for r in cohort_sum["roster"]]
    assert "Ewan t" in names
    assert "Alan" in names


def test_simplified_daily_mobile_and_garmin_2fa(client, monkeypatch):
    # 1. Verify /challenge contains the simplified mobile-first Daily view + Desktop Garmin 2FA input
    res = client.get("/challenge")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "op-btn-sync-garmin" in html
    assert "op-training-btns" in html
    assert "e.g. 3 x 5k at 5 min miles" in html
    assert "Submit Monday" in html
    assert "Weekly Round-Up (Auto-Collated)" in html
    assert "cfg-garmin-mfa-code" in html
    assert "Verify 2FA Code" in html

    # 2. Save Monday daily entry with BOTH (GYM & CARDIO) and workout note, verify weekly round-up collation
    save_res = client.post("/api/challenge/checkins", json={
        "date": "2026-10-19",
        "weight_kg": 83.4,
        "steps": 12450,
        "calories": 2160,
        "protein_g": 155,
        "water_l": 3.8,
        "sleep": "8h 15m",
        "training_type": "GYM & CARDIO",
        "notes": "3 x 5k at 5 min miles",
    }).get_json()
    assert "checkin" in save_res
    assert save_res["checkin"]["training_type"] == "GYM & CARDIO"
    assert save_res["checkin"]["notes"] == "3 x 5k at 5 min miles"
    assert save_res["checkin"]["sleep_mins"] == 495

    ov = client.get("/api/challenge/overview?date=2026-10-19").get_json()
    avgs = ov["current_week_sheet"]["averages"]
    assert avgs["days_logged"] >= 1
    assert avgs["avg_steps"] >= 12450

    # 3. Verify Garmin 2FA challenge propagation via /api/challenge/sync/connect
    import challenge_progress

    def fake_fetch_garmin(email, pw, target_date=None, tokenstore_dir=None, mfa_code=None, **kwargs):
        if not mfa_code:
            return {
                "ok": False,
                "needs_mfa": True,
                "error": "🔐 Garmin 2-Factor Auth: Enter the 6-digit verification code sent by Garmin.",
            }
        return {
            "ok": True,
            "parsed": {
                "steps": 11800,
                "sleep_mins": 480,
                "sleep_str": "8h 00m",
                "parsed_activities": [],
            },
        }

    monkeypatch.setattr(challenge_progress, "fetch_live_garmin_data", fake_fetch_garmin)

    r_mfa = client.post("/api/challenge/sync/connect", json={
        "date": "2026-10-19",
        "garmin_email": "ewan@example.com",
        "garmin_password": "secret",
    }).get_json()
    assert r_mfa["ok"] is True
    assert r_mfa["needs_mfa"] is True
    assert "6-digit" in r_mfa["garmin_status"]

    r_verified = client.post("/api/challenge/sync/connect", json={
        "date": "2026-10-19",
        "garmin_email": "ewan@example.com",
        "garmin_password": "secret",
        "mfa_code": "654321",
    }).get_json()
    assert r_verified["ok"] is True
    assert r_verified["needs_mfa"] is False
    assert "11,800 steps" in r_verified["garmin_status"]


def test_blank_fields_forgot_password_garmin_non2fa_and_apple_health(client, monkeypatch, tmp_path):
    """Verify blank daily inputs, forgot password flow, Garmin non-2FA + 2FA login, and Apple Health workflow."""
    # 1. Daily fields in /challenge have blank placeholders (no target numbers pre-populated)
    ch_html = client.get("/challenge").get_data(as_text=True)
    assert 'id="op-steps" class="op-big-input" placeholder=""' in ch_html
    assert 'id="op-cals" class="op-big-input" placeholder=""' in ch_html
    assert 'id="op-prot" class="op-big-input" placeholder=""' in ch_html
    assert 'id="op-water" class="op-big-input" placeholder=""' in ch_html

    # 2. Forgot password & reset password flow (via Cohort Invite Code & via 6-digit reset_code)
    join_res = client.post("/api/challenge/blocks/join", json={
        "invite_code": "CS-OCT2026",
        "client_name": "Sarah",
        "email": "sarah@example.com",
        "password": "oldpassword123",
    }).get_json()
    assert join_res["ok"] is True

    fp_res = client.post("/api/challenge/auth/forgot-password", json={
        "email": "sarah@example.com",
    }).get_json()
    assert fp_res["ok"] is True

    # Reset using cohort block invite code CS-OCT2026
    rst_res = client.post("/api/challenge/auth/reset-password", json={
        "email": "sarah@example.com",
        "verification": "CS-OCT2026",
        "new_password": "newpassword456",
    }).get_json()
    assert rst_res["ok"] is True

    # Login with old password fails; login with new password succeeds
    bad_login = client.post("/api/challenge/auth/login", json={
        "email": "sarah@example.com",
        "password": "oldpassword123",
    })
    assert bad_login.status_code == 401
    good_login = client.post("/api/challenge/auth/login", json={
        "email": "sarah@example.com",
        "password": "newpassword456",
    }).get_json()
    assert good_login["ok"] is True

    # 3. Apple Health workflow: tokenized webhook URL & 1-click simulate test
    integ_res = client.get("/api/challenge/integrations").get_json()
    webhook_token = integ_res["webhook_token"]
    assert webhook_token.startswith("csf-p")

    # Simulate Apple Health + MFP HealthKit sync
    ah_sim = client.post("/api/challenge/sync/apple-health", json={
        "simulate": True,
        "date": "2026-10-20",
    }).get_json()
    assert ah_sim["ok"] is True
    assert ah_sim["checkin"]["steps"] == 11420
    assert ah_sim["checkin"]["protein_g"] > 0

    # Unauthenticated iOS Shortcut call using ?token=<webhook_token> updates Sarah's profile
    with client.session_transaction() as sess:
        sess.clear()
        sess["challenge_force_unauthed"] = True
    ah_tok = client.post(
        f"/api/challenge/sync/apple-health?token={webhook_token}",
        json={
            "date": "2026-10-21",
            "steps": 13850,
            "sleep_hours": 8.2,
            "weight_kg": 71.4,
            "calories": 1950,
            "protein_g": 148,
            "water_l": 3.5,
        },
    ).get_json()
    assert ah_tok["ok"] is True
    assert ah_tok["profile_id"] == join_res["profile_id"]
    assert ah_tok["checkin"]["steps"] == 13850
    assert ah_tok["checkin"]["calories"] == 1950

    # 4. Garmin non-2FA login works even when return_on_mfa=True is used
    import sys
    import types
    from sync_service import fetch_live_garmin_data

    class FakeGarth:
        profile = {"displayName": "ewan_garmin", "fullName": "Ewan Taylor"}
        def dump(self, path):
            import os
            os.makedirs(path, exist_ok=True)
            with open(os.path.join(path, "oauth1_token.json"), "w") as f:
                f.write("{}")
        def dumps(self):
            return '{"oauth1":"ok"}'
        def loads(self, s):
            pass

    class FakeGarmin:
        def __init__(self, email=None, pw=None, return_on_mfa=False):
            self.email = email
            self.pw = pw
            self.return_on_mfa = return_on_mfa
            self.display_name = None
            self.garth = FakeGarth()
        def login(self, tokenstore=None):
            if tokenstore:
                self.display_name = "ewan_garmin"
                return True
            if self.return_on_mfa:
                # Simulate garminconnect returning early without setting self.display_name
                return ("oauth1_tok", "oauth2_tok")
            self.display_name = "ewan_garmin"
            return True
        def get_stats(self, d):
            assert self.display_name == "ewan_garmin", "display_name must be initialized!"
            return {"totalSteps": 12345, "restingHeartRate": 54, "bodyBatteryMostRecentValue": 82}
        def get_sleep_data(self, d):
            return {"dailySleepDTO": {"sleepTimeSeconds": 28800, "sleepScores": {"overall": {"value": 86}}}}
        def get_body_composition(self, d):
            return {"totalAverage": {"weight": 83200}}
        def get_activities_by_date(self, s, e):
            return []

    fake_mod = types.ModuleType("garminconnect")
    fake_mod.Garmin = FakeGarmin
    monkeypatch.setitem(sys.modules, "garminconnect", fake_mod)

    g_res = fetch_live_garmin_data(
        "taylor.ewan@gmail.com",
        "mygarminpass",
        target_date="2026-10-20",
        tokenstore_dir=str(tmp_path / "garmin_tok"),
        force_relogin=True,
    )
    assert g_res["ok"] is True
    assert g_res["parsed"]["steps"] == 12345
    assert g_res["parsed"]["weight_kg"] == 83.2
    assert g_res["token_dump"] == '{"oauth1":"ok"}'











