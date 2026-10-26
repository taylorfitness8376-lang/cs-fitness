from flask import Blueprint, current_app, jsonify, redirect, request, render_template, session, url_for
from datetime import datetime, timedelta
import csv
import io
import json
import re

from database import get_db
from challenge import (
    _get_active_profile,
    _resolve_webhook_or_active_profile,
    _is_current_user_admin,
    _get_profile_integrations,
    _update_profile_integrations,
    _encode_secret,
    _decode_secret,
    _compute_week_and_day,
    _upsert_checkin,
    _save_daily_activity,
    _sync_checkin_from_activities,
    _build_week_sheet,
)
from sync_service import (
    fetch_live_garmin_data,
    fetch_live_mfp_data,
    format_weekly_telegram_summary,
    send_telegram_message,
)

challenge_progress_bp = Blueprint("challenge_progress", __name__)


def parse_workout_volume_kg(weight_reps_str, target_sets=1):
    """Parse '70kg x8' or '45kg x15, 15, 15' into (sets_count, reps_total, volume_kg)."""
    s = str(weight_reps_str or "").strip()
    if not s:
        return 0, 0, 0.0
    w_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|lb)?", s, re.IGNORECASE)
    weight = float(w_match.group(1)) if w_match else 0.0
    after_x = re.split(r"[x×]", s, maxsplit=1)
    if len(after_x) > 1:
        rep_nums = [int(n) for n in re.findall(r"\d+", after_x[1])]
        sets_c = len(rep_nums) if rep_nums else int(target_sets or 1)
        reps_tot = sum(rep_nums) if rep_nums else 0
    else:
        sets_c = int(target_sets or 1)
        reps_tot = sets_c * 8
    return sets_c, reps_tot, round(weight * reps_tot, 1)


def _ensure_weekly_submissions_table(db):
    db.execute(
        """CREATE TABLE IF NOT EXISTS weekly_submissions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id          INTEGER NOT NULL DEFAULT 1,
            week_num            INTEGER NOT NULL DEFAULT 1,
            status              TEXT NOT NULL DEFAULT 'Submitted',
            challenger_comments TEXT NOT NULL DEFAULT '',
            coach_feedback      TEXT NOT NULL DEFAULT '',
            avg_weight_kg       REAL,
            avg_steps           INTEGER NOT NULL DEFAULT 0,
            avg_calories        INTEGER NOT NULL DEFAULT 0,
            avg_protein_g       INTEGER NOT NULL DEFAULT 0,
            photos_count        INTEGER NOT NULL DEFAULT 0,
            card_data_url       TEXT NOT NULL DEFAULT '',
            submitted_at        TEXT NOT NULL DEFAULT '',
            reviewed_at         TEXT NOT NULL DEFAULT '',
            updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(profile_id, week_num)
        )"""
    )
    try:
        db.execute("ALTER TABLE weekly_submissions ADD COLUMN card_data_url TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass
    db.execute(
        """CREATE TABLE IF NOT EXISTS daily_journey_moments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id      INTEGER NOT NULL DEFAULT 1,
            date            TEXT NOT NULL,
            slot            TEXT NOT NULL DEFAULT 'Breakfast',
            caption         TEXT NOT NULL DEFAULT '',
            hashtags        TEXT NOT NULL DEFAULT '',
            photo_data_url  TEXT NOT NULL DEFAULT '',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(profile_id, date, slot)
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS challenge_user_accounts (
            profile_id      INTEGER PRIMARY KEY,
            username        TEXT NOT NULL UNIQUE,
            password_hash   TEXT NOT NULL DEFAULT '',
            role            TEXT NOT NULL DEFAULT 'challenger',
            email           TEXT NOT NULL DEFAULT '',
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )


def compute_week_over_week(db, profile):
    """Build Week-over-Week summary (Pre-Coaching Wk 0 + Weeks 1..8) with workouts, photos & in-app check-in status."""
    _ensure_weekly_submissions_table(db)
    start_dt = datetime.strptime(profile.get("start_date", "2026-10-19")[:10], "%Y-%m-%d")
    start_w = float(profile.get("start_weight_kg") or 84.0)
    prev_avg_w = start_w
    weeks = []

    subs = {
        r["week_num"]: dict(r)
        for r in db.execute(
            "SELECT * FROM weekly_submissions WHERE profile_id=?", (profile["id"],)
        ).fetchall()
    }

    for wk in range(0, 9):
        sheet = _build_week_sheet(db, profile, wk)
        d0, d1 = sheet["start_date"], sheet["end_date"]
        demo_sources = ("Garmin Fenix 7", "Garmin Connect (Fenix 7 + Index S2)", "Garmin Connect (Simulated)")
        real_rows = [
            r for r in sheet["rows"]
            if r.get("sync_source_garmin") not in demo_sources
            and (r.get("steps", 0) > 0 or r.get("calories", 0) > 0 or r.get("weight_kg") is not None)
        ]
        weights = [float(r["weight_kg"]) for r in real_rows if r.get("weight_kg") is not None]
        avg_w = round(sum(weights) / len(weights), 2) if weights else 0.0
        avg_steps = int(round(sum(int(r.get("steps") or 0) for r in real_rows) / len(real_rows))) if real_rows else 0
        avg_cals = int(round(sum(int(r.get("calories") or 0) for r in real_rows) / len(real_rows))) if real_rows else 0
        avg_prot = int(round(sum(int(r.get("protein_g") or 0) for r in real_rows) / len(real_rows))) if real_rows else 0
        days_on_plan = sum(1 for r in real_rows if r.get("stick_to_plan") == "Y")
        wow_diff = round(avg_w - prev_avg_w, 2) if avg_w > 0 else None
        tot_diff = round(avg_w - start_w, 2) if avg_w > 0 else None
        if avg_w > 0:
            prev_avg_w = avg_w

        acts = db.execute(
            "SELECT category, distance_km, garmin_activity_id FROM daily_activities WHERE profile_id=? AND date>=? AND date<=?",
            (profile["id"], d0, d1),
        ).fetchall()
        real_acts = [
            a for a in acts
            if not str(a["garmin_activity_id"] or "").startswith(("act-101", "garmin-run-", "garmin-gym-"))
        ]
        gym_c = sum(1 for r in real_rows if "GYM" in (r.get("training_type") or ""))
        cardio_c = sum(1 for r in real_rows if "CARDIO" in (r.get("training_type") or ""))
        run_km = round(sum(float(a["distance_km"] or 0) for a in real_acts), 2)

        wlogs = db.execute(
            "SELECT weight_reps, target_sets FROM workout_logs WHERE profile_id=? AND week_num=?",
            (profile["id"], max(1, wk) if wk > 0 else 0),
        ).fetchall()
        active_wlogs = [w for w in wlogs if w["weight_reps"]]
        wk_sets = sum(parse_workout_volume_kg(w["weight_reps"], w["target_sets"])[0] for w in active_wlogs)
        vol_kg = round(sum(parse_workout_volume_kg(w["weight_reps"], w["target_sets"])[2] for w in active_wlogs), 0)

        photos = db.execute(
            "SELECT pose, photo_data_url FROM progress_photos WHERE profile_id=? AND week_num=?",
            (profile["id"], wk),
        ).fetchall()
        poses = [p["pose"] for p in photos]
        sub = subs.get(wk, {})

        weeks.append({
            "week_num": wk,
            "label": "Start (Mon Day 1)" if wk == 0 else ("Week 1 (Fri · No Photos)" if wk == 1 else f"Week {wk} (Fri)"),
            "start_date": d0,
            "end_date": d1,
            "checkin_day": sheet.get("checkin_day", "Monday (Day 1 Start)" if wk == 0 else "Friday"),
            "checkin_date": sheet.get("checkin_date", d0),
            "photos_required": bool(sheet.get("photos_required", wk != 1)),
            "checkin_schedule_note": sheet.get("checkin_schedule_note", ""),
            "days_logged": len(real_rows),
            "days_on_plan": days_on_plan,
            "avg_weight_kg": avg_w if avg_w > 0 else None,
            "target_weight_kg": sheet["target_weight_kg"],
            "wow_diff_kg": wow_diff,
            "weight_change_vs_prev_kg": wow_diff,
            "total_diff_kg": tot_diff,
            "avg_steps": avg_steps,
            "step_target": sheet["step_target"],
            "target_steps": sheet["step_target"],
            "avg_calories": avg_cals,
            "avg_protein_g": avg_prot,
            "gym_sessions": gym_c,
            "cardio_sessions": cardio_c,
            "run_km": run_km,
            "volume_kg": vol_kg,
            "workout_exercises_logged": len(active_wlogs),
            "workout_sets_logged": wk_sets,
            "workout_volume_kg": vol_kg,
            "photos_recorded": len(poses),
            "photos_count": len(poses),
            "poses": poses,
            "poses_logged": poses,
            "submission_status": sub.get("status", "Not Submitted"),
            "challenger_comments": sub.get("challenger_comments", ""),
            "coach_feedback": sub.get("coach_feedback", ""),
            "card_data_url": sub.get("card_data_url", ""),
            "submitted_at": sub.get("submitted_at", ""),
            "reviewed_at": sub.get("reviewed_at", ""),
        })
    return weeks


@challenge_progress_bp.route("/api/challenge/progress/summary", methods=["GET"])
def api_progress_summary():
    db = get_db()
    _ensure_weekly_submissions_table(db)
    profile_id = request.args.get("profile_id", type=int)
    profile = _get_active_profile(db, profile_id)
    week_num = request.args.get("week_num", default=0, type=int)
    wow = compute_week_over_week(db, profile)
    photos = [
        dict(r) for r in db.execute(
            "SELECT * FROM progress_photos WHERE profile_id=? ORDER BY week_num, id", (profile["id"],)
        ).fetchall()
    ]
    wlogs = [
        dict(r) for r in db.execute(
            "SELECT * FROM workout_logs WHERE profile_id=? AND weight_reps != '' ORDER BY updated_at DESC",
            (profile["id"],),
        ).fetchall()
    ]
    tot_sets, tot_vol = 0, 0.0
    for w in wlogs:
        sc, _, vol = parse_workout_volume_kg(w["weight_reps"], w["target_sets"])
        tot_sets += sc
        tot_vol += vol

    is_admin = _is_current_user_admin(db)
    if is_admin:
        all_subs = [
            dict(r) for r in db.execute(
                """SELECT ws.*, cp.client_name, cp.target_calories, cp.target_protein_g, cp.target_water_l
                   FROM weekly_submissions ws
                   LEFT JOIN challenge_profiles cp ON cp.id = ws.profile_id
                   ORDER BY ws.updated_at DESC, ws.week_num DESC"""
            ).fetchall()
        ]
        all_profiles = [
            dict(r) for r in db.execute("SELECT * FROM challenge_profiles ORDER BY id").fetchall()
        ]
    else:
        all_subs = [
            dict(r) for r in db.execute(
                """SELECT ws.*, cp.client_name, cp.target_calories, cp.target_protein_g, cp.target_water_l
                   FROM weekly_submissions ws
                   LEFT JOIN challenge_profiles cp ON cp.id = ws.profile_id
                   WHERE ws.profile_id=?
                   ORDER BY ws.updated_at DESC, ws.week_num DESC""",
                (profile["id"],),
            ).fetchall()
        ]
        all_profiles = [profile]

    daily_moments = [
        dict(r) for r in db.execute(
            "SELECT * FROM daily_journey_moments WHERE profile_id=? ORDER BY date DESC, id ASC LIMIT 60",
            (profile["id"],),
        ).fetchall()
    ]
    return jsonify({
        "ok": True,
        "profile": profile,
        "all_profiles": all_profiles,
        "weeks": wow,
        "week_over_week": wow,
        "photos": photos,
        "daily_moments": daily_moments,
        "weekly_submissions": all_subs,
        "workout_rollup": {
            "exercises_logged": len(wlogs),
            "total_sets": tot_sets,
            "total_volume_kg": round(tot_vol, 0),
        },
        "active_week_num": week_num,
    })


@challenge_progress_bp.route("/api/challenge/weekly-checkin/submit", methods=["POST"])
def api_submit_weekly_checkin():
    """Submit a challenger's weekly check-in inside the app (with comments, averages & 3 photos)."""
    db = get_db()
    _ensure_weekly_submissions_table(db)
    data = request.get_json() or {}
    profile = _get_active_profile(db, data.get("profile_id"))
    pid = profile["id"]
    week_num = int(data.get("week_num", 1))
    comments = (data.get("challenger_comments") or "").strip()
    card_data_url = data.get("card_data_url") or ""

    wow = compute_week_over_week(db, profile)
    wk_row = next((w for w in wow if w["week_num"] == week_num), {})
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    existing = db.execute(
        "SELECT id, coach_feedback, status, card_data_url FROM weekly_submissions WHERE profile_id=? AND week_num=?",
        (pid, week_num),
    ).fetchone()
    if existing:
        new_status = "Reviewed" if existing["coach_feedback"] else "Submitted"
        final_card = card_data_url or existing["card_data_url"] or ""
        db.execute(
            """UPDATE weekly_submissions SET
                status=?, challenger_comments=?, avg_weight_kg=?, avg_steps=?,
                avg_calories=?, avg_protein_g=?, photos_count=?, card_data_url=?, submitted_at=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (
                new_status, comments, wk_row.get("avg_weight_kg"),
                int(wk_row.get("avg_steps") or 0), int(wk_row.get("avg_calories") or 0),
                int(wk_row.get("avg_protein_g") or 0), int(wk_row.get("photos_count") or 0),
                final_card, now_str, existing["id"],
            ),
        )
    else:
        db.execute(
            """INSERT INTO weekly_submissions
               (profile_id, week_num, status, challenger_comments, avg_weight_kg, avg_steps, avg_calories, avg_protein_g, photos_count, card_data_url, submitted_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                pid, week_num, "Submitted", comments, wk_row.get("avg_weight_kg"),
                int(wk_row.get("avg_steps") or 0), int(wk_row.get("avg_calories") or 0),
                int(wk_row.get("avg_protein_g") or 0), int(wk_row.get("photos_count") or 0),
                card_data_url, now_str,
            ),
        )
    db.commit()
    return jsonify({"ok": True, "week_num": week_num, "status": "Submitted", "submitted_at": now_str})


@challenge_progress_bp.route("/api/challenge/weekly-checkin/review", methods=["POST"])
def api_review_weekly_checkin():
    """Coach Chris saves in-app weekly check-in feedback & optional target adjustments."""
    db = get_db()
    _ensure_weekly_submissions_table(db)
    data = request.get_json() or {}
    active_prof = _get_active_profile(db)
    pid = int(data.get("profile_id") or active_prof["id"])
    if pid != int(active_prof["id"]) and not _is_current_user_admin(db):
        return jsonify({"ok": False, "error": "Only Admin coaches can review another challenger's check-in"}), 403
    week_num = int(data.get("week_num", 1))
    feedback = (data.get("coach_feedback") or "").strip()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    existing = db.execute(
        "SELECT id FROM weekly_submissions WHERE profile_id=? AND week_num=?", (pid, week_num)
    ).fetchone()
    if existing:
        db.execute(
            """UPDATE weekly_submissions SET
                status='Reviewed', coach_feedback=?, reviewed_at=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (feedback, now_str, existing["id"]),
        )
    else:
        db.execute(
            """INSERT INTO weekly_submissions
               (profile_id, week_num, status, coach_feedback, reviewed_at)
               VALUES (?,?,'Reviewed',?,?)""",
            (pid, week_num, feedback, now_str),
        )

    if data.get("new_target_calories") or data.get("new_target_protein_g"):
        prof = dict(db.execute("SELECT * FROM challenge_profiles WHERE id=?", (pid,)).fetchone())
        cals = int(data.get("new_target_calories") or prof["target_calories"])
        prot = int(data.get("new_target_protein_g") or prof["target_protein_g"])
        db.execute(
            "UPDATE challenge_profiles SET target_calories=?, target_protein_g=? WHERE id=?",
            (cals, prot, pid),
        )
    db.commit()
    return jsonify({"ok": True, "week_num": week_num, "status": "Reviewed", "reviewed_at": now_str})


@challenge_progress_bp.route("/api/challenge/profile/update", methods=["POST"])
def api_update_profile_settings():
    """Update active user's profile/targets or add a new challenger user."""
    from database import calculate_challenge_targets
    db = get_db()
    data = request.get_json() or {}
    active_prof = _get_active_profile(db)
    pid = int(data.get("profile_id") or active_prof["id"])
    if pid != int(active_prof["id"]) and not _is_current_user_admin(db):
        pid = int(active_prof["id"])
    prof = dict(db.execute("SELECT * FROM challenge_profiles WHERE id=?", (pid,)).fetchone())

    start_w = float(data.get("start_weight_kg") or prof["start_weight_kg"])
    target_w = float(data.get("target_weight_kg") or prof["target_weight_kg"])
    start_bf = float(data.get("start_body_fat_pct") or prof["start_body_fat_pct"])
    target_bf = float(data.get("target_body_fat_pct") or prof["target_body_fat_pct"])
    start_date = (data.get("start_date") or prof["start_date"])[:10]
    prot = int(data.get("target_protein_g") or prof["target_protein_g"])

    calc = calculate_challenge_targets(
        start_weight_kg=start_w,
        target_weight_kg=target_w,
        start_body_fat_pct=start_bf,
        target_body_fat_pct=target_bf,
        protein_g=prot,
        start_date=start_date,
        goal=data.get("goal") or prof["goal"],
        returning_member=bool(data.get("returning_member", prof["returning_member"])),
    )
    cals = int(data.get("target_calories") or calc["target_calories"])
    water_l = float(data.get("target_water_l") or calc["target_water_l"])

    db.execute(
        """UPDATE challenge_profiles SET
            start_date=?, end_date=?, start_weight_kg=?, target_weight_kg=?,
            start_body_fat_pct=?, target_body_fat_pct=?, lean_body_mass_kg=?, fat_mass_kg=?, to_lose_kg=?,
            target_calories=?, target_protein_g=?, target_fats_g=?, target_carbs_g=?, target_water_l=?,
            weekly_targets_json=?
           WHERE id=?""",
        (
            calc["start_date"], calc["end_date"], start_w, target_w,
            start_bf, target_bf, calc["lean_body_mass_kg"], calc["fat_mass_kg"], calc["to_lose_kg"],
            cals, prot, calc["target_fats_g"], calc["target_carbs_g"], water_l,
            json.dumps(calc["weekly_targets"]), pid,
        ),
    )
    db.commit()
    return jsonify({"ok": True, "profile": _get_active_profile(db, pid)})


@challenge_progress_bp.route("/api/challenge/clear-fake-data", methods=["POST"])
def api_clear_fake_data():
    """Remove pre-seeded demo/simulated check-in and activity rows when requested by the user."""
    db = get_db()
    db.execute(
        "DELETE FROM daily_checkins WHERE sync_source_garmin IN ('Garmin Fenix 7', 'Garmin Connect (Fenix 7 + Index S2)', 'Garmin Connect (Simulated)')"
    )
    db.execute(
        "DELETE FROM daily_activities WHERE garmin_activity_id LIKE 'act-101%' OR garmin_activity_id LIKE 'garmin-%'"
    )
    db.commit()
    return jsonify({"ok": True, "message": "Cleared demo data. Only real logged data will be shown."})


@challenge_progress_bp.route("/api/challenge/photos/upload", methods=["POST"])
def api_upload_week_photo():
    """Save or update one of the 3 weekly progress photos (Front, Side, Back) with real image data."""
    db = get_db()
    pid = _get_active_profile(db)["id"]
    data = request.get_json() or {}
    week_num = int(data.get("week_num", 0))
    pose = data.get("pose", "Front")
    if pose not in ("Front", "Side", "Back"):
        pose = "Front"
    taken_date = (data.get("taken_date") or datetime.now().strftime("%Y-%m-%d"))[:10]
    weight_kg = data.get("weight_kg")
    photo_data_url = data.get("photo_data_url", "")
    notes = data.get("notes", "")

    existing = db.execute(
        "SELECT id FROM progress_photos WHERE profile_id=? AND week_num=? AND pose=?",
        (pid, week_num, pose),
    ).fetchone()
    if existing:
        db.execute(
            "UPDATE progress_photos SET taken_date=?, weight_kg=?, photo_data_url=?, notes=?, fasted_confirmed=1 WHERE id=?",
            (taken_date, weight_kg, photo_data_url, notes, existing["id"]),
        )
    else:
        db.execute(
            """INSERT INTO progress_photos (profile_id, week_num, pose, taken_date, weight_kg, fasted_confirmed, photo_data_url, notes)
               VALUES (?,?,?,?,?,1,?,?)""",
            (pid, week_num, pose, taken_date, weight_kg, photo_data_url, notes),
        )
    db.commit()
    photos = [
        dict(r) for r in db.execute(
            "SELECT * FROM progress_photos WHERE profile_id=? ORDER BY week_num, id", (pid,)
        ).fetchall()
    ]
    return jsonify({"ok": True, "week_num": week_num, "pose": pose, "photos": photos})


@challenge_progress_bp.route("/api/challenge/workouts/rollup", methods=["POST"])
def api_workout_rollup():
    """Roll up logged exercises from Tab 2 into Today's Activities & Check-In Sheet."""
    db = get_db()
    pid = _get_active_profile(db)["id"]
    data = request.get_json() or {}
    track = data.get("track", "mens")
    workout_num = int(data.get("workout_num", 1))
    week_num = int(data.get("week_num", 1))
    date_str = (data.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]

    rows = db.execute(
        "SELECT exercise_name, weight_reps, target_sets FROM workout_logs WHERE profile_id=? AND track=? AND workout_num=? AND week_num=? AND weight_reps != ''",
        (pid, track, workout_num, week_num),
    ).fetchall()
    title = f"{track.title()} Workout {workout_num}"
    if not rows:
        db.execute(
            "DELETE FROM daily_activities WHERE profile_id=? AND date=? AND title=?",
            (pid, date_str, title),
        )
        db.commit()
        checkin = _sync_checkin_from_activities(db, date_str, pid)
        return jsonify({"ok": True, "rolled_up": False, "checkin": checkin})

    tot_sets, tot_vol = 0, 0.0
    lifts = []
    for r in rows:
        sc, _, vol = parse_workout_volume_kg(r["weight_reps"], r["target_sets"])
        tot_sets += sc
        tot_vol += vol
        lifts.append(f"{r['exercise_name']} ({r['weight_reps']})")

    notes = f"Wk {week_num}: {len(rows)} exercises · {tot_sets} sets · {int(tot_vol):,} kg volume — " + ", ".join(lifts[:3])
    _save_daily_activity(
        db,
        {
            "date": date_str,
            "source": "Strength Logger",
            "activity_type": "strength",
            "category": "GYM",
            "title": title,
            "duration_mins": 50,
            "notes": notes,
            "manual_add": True,
        },
        pid,
    )
    checkin = _sync_checkin_from_activities(db, date_str, pid)
    return jsonify({"ok": True, "rolled_up": True, "volume_kg": round(tot_vol, 0), "sets": tot_sets, "checkin": checkin})


@challenge_progress_bp.route("/api/challenge/sync/connect", methods=["POST"])
def api_sync_connect_and_save():
    """Save Garmin/MFP/Telegram details, attempt live login/sync, and return detailed status."""
    import os
    db = get_db()
    data = request.get_json() or {}
    profile = _get_active_profile(db)
    pid = int(profile["id"])
    date_str = (data.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
    curr = _get_profile_integrations(db, pid, include_secrets=True)

    for k in ("garmin_email", "mfp_username", "nutrition_provider", "telegram_bot_token", "telegram_chat_id", "coach_telegram_handle"):
        if k in data and data[k] is not None:
            curr[k] = str(data[k]).strip()

    raw_req_pass = data.get("garmin_password") or ""
    if raw_req_pass:
        curr["garmin_password_set"] = 1
        curr["garmin_password_b64"] = _encode_secret(raw_req_pass)
    saved_pass = _decode_secret(curr.get("garmin_password_b64", ""))
    garmin_pass = raw_req_pass or saved_pass
    saved_token_dump = curr.get("garmin_token_dump") or ""
    mfa_code = str(data.get("mfa_code") or "").strip()

    garmin_status = "Not configured — enter Garmin email & password above."
    mfp_status = "Not configured — enter MyFitnessPal username above."
    token_dir = os.path.expanduser("~/.garminconnect") if pid == 1 else os.path.expanduser(f"~/.garminconnect_p{pid}")
    needs_mfa = False
    needs_password = False

    if (
        curr["garmin_email"]
        or mfa_code
        or saved_token_dump
        or os.path.exists(token_dir)
        or os.path.exists(f"{token_dir}_session.json")
    ):
        g_res = fetch_live_garmin_data(
            curr["garmin_email"],
            garmin_pass,
            target_date=date_str,
            tokenstore_dir=token_dir,
            mfa_code=mfa_code,
            saved_token_dump=saved_token_dump,
            force_relogin=bool(raw_req_pass and not mfa_code),
        )
        if g_res.get("ok"):
            curr["garmin_connected"] = 1
            curr["garmin_last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            if g_res.get("token_dump"):
                curr["garmin_token_dump"] = g_res["token_dump"]
            parsed = g_res["parsed"]
            for act in parsed.get("parsed_activities", []):
                _save_daily_activity(db, act, pid)
            _upsert_checkin(db, date_str, parsed, pid)
            if parsed.get("parsed_activities"):
                _sync_checkin_from_activities(db, date_str, pid)
            garmin_status = f"✅ Connected & synced ({parsed.get('steps', 0):,} steps pulled for {date_str})"
        else:
            needs_mfa = bool(g_res.get("needs_mfa"))
            needs_password = bool(g_res.get("needs_password"))
            if needs_mfa:
                garmin_status = g_res.get("error") or "🔐 Enter your 6-digit Garmin 2FA verification code below."
            else:
                garmin_status = f"⚠️ Saved email ({curr['garmin_email']}), live pull note: {g_res.get('error')}"

    mfp_status = "✍️ Add manually in Daily View (Calories, Protein & Water)"

    saved_integ = _update_profile_integrations(db, pid, curr)
    return jsonify({
        "ok": True,
        "needs_mfa": needs_mfa,
        "needs_password": needs_password,
        "integrations": saved_integ,
        "garmin_status": garmin_status,
        "mfp_status": mfp_status,
    })


@challenge_progress_bp.route("/api/challenge/sync/import-data", methods=["POST"])
def api_sync_import_data():
    """Import real Garmin Connect CSV/JSON or MyFitnessPal CSV export into daily_checkins."""
    import csv
    import io
    db = get_db()
    profile = _get_active_profile(db)
    pid = int(profile["id"])
    data = request.get_json() or {}
    source = data.get("source", "garmin")
    raw_text = (data.get("content") or "").strip()
    date_fallback = (data.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
    if not raw_text:
        return jsonify({"ok": False, "error": "Empty file content"}), 400

    imported_dates = []
    if raw_text.startswith("{") or raw_text.startswith("["):
        payload = json.loads(raw_text)
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            d = (item.get("date") or item.get("calendarDate") or date_fallback)[:10]
            if source == "garmin":
                from sync_service import parse_garmin_payload
                parsed = parse_garmin_payload(item)
                for act in parsed.get("parsed_activities", []):
                    _save_daily_activity(db, act, pid)
                _upsert_checkin(db, d, parsed, pid)
            elif source == "apple_health":
                from sync_service import parse_apple_health_payload
                parsed = parse_apple_health_payload(item, target_date=d)
                for act in parsed.get("parsed_activities", []):
                    _save_daily_activity(db, act, pid)
                _upsert_checkin(db, d, parsed, pid)
            else:
                from sync_service import parse_nutrition_payload
                item["provider"] = "MyFitnessPal CSV"
                _upsert_checkin(db, d, parse_nutrition_payload(item), pid)
            imported_dates.append(d)
    else:
        reader = csv.DictReader(io.StringIO(raw_text))
        for row in reader:
            norm = {str(k).strip().lower(): str(v).strip() for k, v in row.items() if k}
            d = (norm.get("date") or norm.get("calendar date") or date_fallback)[:10]
            if source == "garmin":
                from sync_service import parse_garmin_payload
                parsed = parse_garmin_payload({
                    "date": d,
                    "steps": int(float(norm.get("steps") or norm.get("total steps") or 0)),
                    "weight_kg": float(norm["weight"]) if norm.get("weight") else None,
                    "resting_hr": int(float(norm["resting heart rate"])) if norm.get("resting heart rate") else None,
                })
                _upsert_checkin(db, d, parsed, pid)
            elif source == "apple_health":
                from sync_service import parse_apple_health_payload
                parsed = parse_apple_health_payload({
                    "date": d,
                    "steps": int(float(norm.get("steps") or norm.get("step count") or norm.get("step_count") or 0)) if any(norm.get(k) for k in ("steps", "step count", "step_count")) else None,
                    "sleep_hours": float(norm.get("sleep") or norm.get("sleep analysis") or 0) if any(norm.get(k) for k in ("sleep", "sleep analysis")) else None,
                    "weight_kg": float(norm.get("weight") or norm.get("body mass") or 0) if any(norm.get(k) for k in ("weight", "body mass")) else None,
                    "calories": int(float(norm.get("dietary energy") or norm.get("calories") or 0)) if any(norm.get(k) for k in ("dietary energy", "calories")) else None,
                    "protein_g": int(float(norm.get("protein") or norm.get("protein (g)") or 0)) if any(norm.get(k) for k in ("protein", "protein (g)")) else None,
                    "carbs_g": int(float(norm.get("carbohydrates") or norm.get("carbs") or 0)) if any(norm.get(k) for k in ("carbohydrates", "carbs")) else None,
                    "fats_g": int(float(norm.get("total fat") or norm.get("fat") or 0)) if any(norm.get(k) for k in ("total fat", "fat")) else None,
                    "fibre_g": int(float(norm.get("fiber") or norm.get("fibre") or 0)) if any(norm.get(k) for k in ("fiber", "fibre")) else None,
                    "water_l": float(norm.get("dietary water") or norm.get("water") or 0) if any(norm.get(k) for k in ("dietary water", "water")) else None,
                }, target_date=d)
                _upsert_checkin(db, d, parsed, pid)
            else:
                from sync_service import parse_nutrition_payload
                parsed = parse_nutrition_payload({
                    "date": d,
                    "provider": "MyFitnessPal CSV",
                    "calories": int(float(norm.get("calories") or 0)),
                    "protein_g": int(float(norm.get("protein (g)") or norm.get("protein") or 0)),
                    "carbs_g": int(float(norm.get("carbohydrates (g)") or norm.get("carbs") or 0)),
                    "fats_g": int(float(norm.get("fat (g)") or norm.get("fat") or 0)),
                    "fibre_g": int(float(norm.get("fiber") or norm.get("fibre") or 0)),
                })
                _upsert_checkin(db, d, parsed, pid)
            imported_dates.append(d)

    return jsonify({"ok": True, "imported_count": len(imported_dates), "dates": imported_dates})


@challenge_progress_bp.route("/api/challenge/sync/apple-health", methods=["POST"])
def api_sync_apple_health():
    """Receive Apple Health + MyFitnessPal HealthKit payload from iOS Shortcut, Health Auto Export, or test simulator."""
    from sync_service import parse_apple_health_payload
    db = get_db()
    data = request.get_json(silent=True) or {}
    profile = _resolve_webhook_or_active_profile(db, data)
    pid = int(profile["id"])
    date_str = (data.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
    if data.get("simulate"):
        data = {
            "date": date_str,
            "steps": data.get("steps") or 11420,
            "sleep_hours": data.get("sleep_hours") or 7.8,
            "weight_kg": data.get("weight_kg") or round(float(profile.get("start_weight_kg") or 83.4), 1),
            " resting_hr": 56,
            "calories": data.get("calories") or int(profile.get("target_calories") or 2173),
            "protein_g": data.get("protein_g") or int(profile.get("target_protein_g") or 150),
            "carbs_g": 215,
            "fats_g": 68,
            "water_l": data.get("water_l") or round(float(profile.get("target_water_l") or 3.66), 2),
            "workouts": data.get("workouts") or [
                {"type": "TraditionalStrengthTraining", "name": "Apple Watch Strength Session", "duration_mins": 48, "calories": 340}
            ],
            "source": "Apple Health + MFP (iOS Shortcut Test)",
        }
    parsed = parse_apple_health_payload(data, target_date=date_str)
    for act in parsed.get("parsed_activities", []):
        _save_daily_activity(db, act, pid)
    saved = _upsert_checkin(db, date_str, parsed, pid)
    if parsed.get("parsed_activities"):
        saved = _sync_checkin_from_activities(db, date_str, pid)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    _update_profile_integrations(
        db, pid, {"garmin_last_sync": now_str, "nutrition_last_sync": now_str, "nutrition_connected": 1}
    )
    db.commit()
    return jsonify({
        "ok": True,
        "source": data.get("source") or "Apple Health (+ MFP HealthKit)",
        "date": date_str,
        "profile_id": pid,
        "parsed": parsed,
        "checkin": saved,
    })


@challenge_progress_bp.route("/challenge/mobile")
def challenge_mobile_page():
    """Super clean 1-page mobile web app for Daily (Meal Pics, Stats, Workouts, Events) & Weekly Check-In."""
    if not session.get("challenge_authed") and (
        not current_app.config.get("TESTING") or session.get("challenge_force_unauthed")
    ):
        return redirect(url_for("challenge_blocks.challenge_login_page"))
    return render_template("challenge.html")


@challenge_progress_bp.route("/api/challenge/daily-moments", methods=["GET", "POST", "DELETE"])
def api_daily_journey_moments():
    """Get, upload, or delete daily meal/workout/event journey photos & captions (updates Coach app live)."""
    db = get_db()
    _ensure_weekly_submissions_table(db)
    profile = _get_active_profile(db, request.args.get("profile_id", type=int))
    pid = profile["id"]

    if request.method == "GET":
        date_str = request.args.get("date")
        if date_str:
            rows = db.execute(
                "SELECT * FROM daily_journey_moments WHERE profile_id=? AND date=? ORDER BY id ASC",
                (pid, date_str[:10]),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM daily_journey_moments WHERE profile_id=? ORDER BY date DESC, id ASC LIMIT 50",
                (pid,),
            ).fetchall()
        return jsonify({"ok": True, "moments": [dict(r) for r in rows]})

    data = request.get_json() or {}
    date_str = (data.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
    slot = (data.get("slot") or "Breakfast").strip()

    if request.method == "DELETE":
        db.execute(
            "DELETE FROM daily_journey_moments WHERE profile_id=? AND date=? AND slot=?",
            (pid, date_str, slot),
        )
        db.commit()
        rows = db.execute(
            "SELECT * FROM daily_journey_moments WHERE profile_id=? AND date=? ORDER BY id ASC",
            (pid, date_str),
        ).fetchall()
        return jsonify({"ok": True, "moments": [dict(r) for r in rows]})

    caption = (data.get("caption") or "").strip()
    first_name = re.sub(r"[^A-Za-z0-9]", "", (profile.get("client_name") or "Ewan").split()[0])
    slot_tag = re.sub(r"[^a-z0-9]", "", slot.split()[0].lower())
    hashtags = (data.get("hashtags") or f"#{first_name} #{slot_tag}").strip()
    photo_data_url = data.get("photo_data_url") or ""

    db.execute(
        """INSERT INTO daily_journey_moments (profile_id, date, slot, caption, hashtags, photo_data_url)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(profile_id, date, slot) DO UPDATE SET
               caption=excluded.caption,
               hashtags=excluded.hashtags,
               photo_data_url=CASE WHEN excluded.photo_data_url != '' THEN excluded.photo_data_url ELSE daily_journey_moments.photo_data_url END,
               created_at=CURRENT_TIMESTAMP""",
        (pid, date_str, slot, caption, hashtags, photo_data_url),
    )
    db.commit()
    rows = db.execute(
        "SELECT * FROM daily_journey_moments WHERE profile_id=? AND date=? ORDER BY id ASC",
        (pid, date_str),
    ).fetchall()
    return jsonify({"ok": True, "date": date_str, "moments": [dict(r) for r in rows]})





