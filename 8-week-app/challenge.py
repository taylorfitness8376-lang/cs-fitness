from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for
from datetime import datetime, timedelta
import json
import re

from database import get_db, calculate_challenge_targets
from sync_service import (
    CS_FITNESS_TIMETABLE,
    format_sleep_minutes,
    parse_sleep_to_minutes,
    format_pace_per_km,
    parse_garmin_activity_details,
    map_cs_class_to_training_type,
    parse_garmin_payload,
    parse_nutrition_payload,
    fetch_live_garmin_data,
    fetch_live_mfp_data,
    generate_simulated_sync_payload,
    format_daily_whatsapp_caption,
    format_weekly_telegram_summary,
    send_telegram_message,
    parse_whatsapp_export,
)

challenge_bp = Blueprint("challenge", __name__)

WORKOUT_TEMPLATES = {
    "mens": [
        {
            "workout_num": 1,
            "title": "WORKOUT 1 - FULL BODY",
            "rep_note": "All exercises to be performed as per the reps stated. Aim for the maximum rep range and no less than the minimum. If you cannot achieve these numbers, adjust the weight to suit.",
            "rows": [
                {"row_key": "W1_A_1", "order": "A", "exercise": "Barbell Back Squat", "notes": "These 3 exercises are all working sets and should challenge you. As you are decreasing reps, the weight should be increasing.", "sets": 1, "reps": "8", "rest": 90, "example": "70kg x8"},
                {"row_key": "W1_A_2", "order": "A", "exercise": "Barbell Back Squat", "notes": "Increase weight from set of 8", "sets": 1, "reps": "6", "rest": 90, "example": "80kg x6"},
                {"row_key": "W1_A_3", "order": "A", "exercise": "Barbell Back Squat", "notes": "Increase weight from set of 6", "sets": 1, "reps": "4", "rest": 90, "example": "90kg x4"},
                {"row_key": "W1_A_4", "order": "A", "exercise": "Barbell Back Squat", "notes": "Top heavy double", "sets": 1, "reps": "2", "rest": 90, "example": "100kg x2"},
                {"row_key": "W1_B_1", "order": "B", "exercise": "Barbell Bench Press", "notes": "Working set — build weight as reps drop, then 15-rep back-off set", "sets": 1, "reps": "9", "rest": 90, "example": "40kg x9"},
                {"row_key": "W1_B_2", "order": "B", "exercise": "Barbell Bench Press", "notes": "Increase weight", "sets": 1, "reps": "6", "rest": 90, "example": "50kg x6"},
                {"row_key": "W1_B_3", "order": "B", "exercise": "Barbell Bench Press", "notes": "2 heavy sets of 4", "sets": 2, "reps": "4", "rest": 90, "example": "60kg x4, 4"},
                {"row_key": "W1_B_4", "order": "B", "exercise": "Barbell Bench Press", "notes": "Back-off high-rep pump set", "sets": 1, "reps": "15", "rest": 90, "example": "40kg x15"},
                {"row_key": "W1_C_1", "order": "C", "exercise": "Deadlift", "notes": "Working sets — increase weight as reps decrease", "sets": 1, "reps": "8", "rest": 60, "example": "60kg x8"},
                {"row_key": "W1_C_2", "order": "C", "exercise": "Deadlift", "notes": "Increase weight", "sets": 1, "reps": "5", "rest": 60, "example": "70kg x5"},
                {"row_key": "W1_C_3", "order": "C", "exercise": "Deadlift", "notes": "2 heavy triples", "sets": 2, "reps": "3", "rest": 60, "example": "80kg x3, 3"},
                {"row_key": "W1_D1_1", "order": "D1", "exercise": "Leg Extentions", "notes": "Hard contraction at the top of each rep", "sets": 3, "reps": "15", "rest": 60, "example": "40kg x10, 10, 10"},
                {"row_key": "W1_D2_1", "order": "D2", "exercise": "Press Ups", "notes": "Perform weighted if possible", "sets": 3, "reps": "15", "rest": 60, "example": "BW x15, 15, 15"},
                {"row_key": "W1_E1_1", "order": "E1", "exercise": "French Press", "notes": "Find a comfortable position for you on these", "sets": 3, "reps": "15", "rest": 60, "example": "25kg x15, 15, 15"},
                {"row_key": "W1_E2_1", "order": "E2", "exercise": "Hammer Curls", "notes": "Two arms at same time", "sets": 3, "reps": "12", "rest": 60, "example": "16kg x12, 12, 12"},
            ],
        },
        {
            "workout_num": 2,
            "title": "WORKOUT 2 - UPPER BODY",
            "rep_note": "All exercises to be performed as per the reps stated. Aim for the maximum rep range and no less than the minimum. If you cannot achieve these numbers, adjust the weight to suit.",
            "rows": [
                {"row_key": "W2_A_1", "order": "A", "exercise": "Seated Barbell Shoulder Press", "notes": "Select the same weight for 10 reps then increase for the sets of 6", "sets": 2, "reps": "10", "rest": 90, "example": "40kg x10, 10"},
                {"row_key": "W2_A_2", "order": "A", "exercise": "Seated Barbell Shoulder Press", "notes": "Increase weight for sets of 6", "sets": 2, "reps": "6", "rest": 90, "example": "50kg x6, 6"},
                {"row_key": "W2_B_1", "order": "B", "exercise": "Bent Over Row", "notes": "Select the same weight for 10 reps then increase for the sets of 6", "sets": 2, "reps": "10", "rest": 90, "example": "20kg x10, 10"},
                {"row_key": "W2_B_2", "order": "B", "exercise": "Bent Over Row", "notes": "Increase weight for sets of 6", "sets": 2, "reps": "6", "rest": 90, "example": "30kg x6, 6"},
                {"row_key": "W2_C1_1", "order": "C1", "exercise": "Alternating Dumbbell Bench Press", "notes": "10 reps each arm", "sets": 3, "reps": "10", "rest": 90, "example": "24kg x10, 10, 10"},
                {"row_key": "W2_C2_1", "order": "C2", "exercise": "Chest Supported Row", "notes": "Find comfortable position that you are stable in", "sets": 3, "reps": "10", "rest": 90, "example": "22kg x10, 10, 10"},
                {"row_key": "W2_D1_1", "order": "D1", "exercise": "Arnold Press", "notes": "Controlled movement", "sets": 3, "reps": "10", "rest": 60, "example": "18kg x10, 10, 10"},
                {"row_key": "W2_D2_1", "order": "D2", "exercise": "Dumbbell Side Raises", "notes": "These wont need to be heavy", "sets": 3, "reps": "12", "rest": 60, "example": "10kg x12, 12, 12"},
                {"row_key": "W2_D3_1", "order": "D3", "exercise": "Front Plate Raises", "notes": "10-15kg max weight", "sets": 3, "reps": "12", "rest": 60, "example": "15kg x12, 12, 12"},
                {"row_key": "W2_E1_1", "order": "E1", "exercise": "Close Grip Lat Pull Down", "notes": "Make sure to control the movement", "sets": 3, "reps": "10", "rest": 60, "example": "55kg x10, 10, 10"},
                {"row_key": "W2_E2_1", "order": "E2", "exercise": "Cable Curls", "notes": "Small pause, squeeze biceps at top", "sets": 3, "reps": "15", "rest": 60, "example": "25kg x15, 15, 15"},
            ],
        },
        {
            "workout_num": 3,
            "title": "WORKOUT 3 - LOWER BODY",
            "rep_note": "All exercises to be performed as per the reps stated. Aim for the maximum rep range and no less than the minimum. If you cannot achieve these numbers, adjust the weight to suit.",
            "rows": [
                {"row_key": "W3_A_1", "order": "A", "exercise": "Leg Press", "notes": "Increase the weight as the reps decrease", "sets": 2, "reps": "15", "rest": 90, "example": "140kg x15, 15"},
                {"row_key": "W3_A_2", "order": "A", "exercise": "Leg Press", "notes": "Increase weight", "sets": 2, "reps": "10", "rest": 90, "example": "180kg x10, 10"},
                {"row_key": "W3_A_3", "order": "A", "exercise": "Leg Press", "notes": "Heavy top set of 8", "sets": 1, "reps": "8", "rest": 90, "example": "210kg x8"},
                {"row_key": "W3_B_1", "order": "B", "exercise": "Dumbbell Romanian Deadlift", "notes": "Dumbbells or Barbell is great", "sets": 4, "reps": "10", "rest": 90, "example": "16kg x 10, 10, 10, 10"},
                {"row_key": "W3_C_1", "order": "C", "exercise": "Bulgarian Split Squats", "notes": "On last set on 12th rep, hold at bottom for 10s, drop the weight, then perform 12 bodyweight reps", "sets": 3, "reps": "12", "rest": 90, "example": "16kg x12, 12, 12"},
                {"row_key": "W3_D1_1", "order": "D1", "exercise": "Leg Extentions", "notes": "Strict form and pause at the top of the rep", "sets": 3, "reps": "12", "rest": 60, "example": "45kg x12, 12, 12"},
                {"row_key": "W3_D2_1", "order": "D2", "exercise": "KB Swings", "notes": "You should manage a fairly heavy weight", "sets": 3, "reps": "15", "rest": 60, "example": "24kg x15, 15, 15"},
                {"row_key": "W3_E1_1", "order": "E1", "exercise": "Calf Raises", "notes": "Using dumbbells, perform these until failure, rest then repeat twice more", "sets": 3, "reps": "MAX", "rest": 60, "example": "20kg xMAX"},
            ],
        },
        {
            "workout_num": 4,
            "title": "WORKOUT 4 - CHEST & BACK",
            "rep_note": "All exercises to be performed as per the reps stated. Aim for the maximum rep range and no less than the minimum. If you cannot achieve these numbers, adjust the weight to suit.",
            "rows": [
                {"row_key": "W4_A_1", "order": "A", "exercise": "Flat Dumbbell Chest Press", "notes": "Progressively heavier on your 6 rep sets", "sets": 2, "reps": "10", "rest": 90, "example": "28kg x10, 10"},
                {"row_key": "W4_A_2", "order": "A", "exercise": "Flat Dumbbell Chest Press", "notes": "Heavier on 6 rep sets", "sets": 2, "reps": "6", "rest": 90, "example": "34kg x6, 6"},
                {"row_key": "W4_B_1", "order": "B", "exercise": "Chin Ups", "notes": "Band assisted or assisted machine is great too", "sets": 4, "reps": "6-8", "rest": 90, "example": "BW x8, 8, 7, 6"},
                {"row_key": "W4_C_1", "order": "C", "exercise": "Single Arm Dumbbell Row", "notes": "Find a comfortable position where you can get the max contraction", "sets": 3, "reps": "10", "rest": 90, "example": "14kg x 12,12,10"},
                {"row_key": "W4_D1_1", "order": "D1", "exercise": "Straight Arm Lat Pull Downs", "notes": "Use a rope or straight bar attachment", "sets": 3, "reps": "12", "rest": 60, "example": "25kg x12, 12, 12"},
                {"row_key": "W4_D2_1", "order": "D2", "exercise": "Deficit Push Ups", "notes": "Elevate feet on bench or box", "sets": 3, "reps": "12", "rest": 60, "example": "BW x12, 12, 12"},
                {"row_key": "W4_E1_1", "order": "E1", "exercise": "Cable Flys", "notes": "Use the low or high set up for these", "sets": 3, "reps": "10-12", "rest": 60, "example": "15kg x12, 12, 10"},
                {"row_key": "W4_E2_1", "order": "E2", "exercise": "Dumbbell Hammer Curls", "notes": "Perform with both dumbbells simultaneously", "sets": 3, "reps": "15", "rest": 60, "example": "14kg x15, 15, 15"},
            ],
        },
    ],
    "ladies": [
        {
            "workout_num": 1,
            "title": "WORKOUT 1 - FULL BODY",
            "rep_note": "All exercises to be performed as per the reps stated. Aim for the maximum rep range and no less than the minimum.",
            "rows": [
                {"row_key": "LW1_A_1", "order": "A", "exercise": "Barbell Back Squat", "notes": "After warm up, find weight you can stick with for all 4 sets", "sets": 4, "reps": "6", "rest": 90, "example": "45kg x6, 6, 6, 6"},
                {"row_key": "LW1_B_1", "order": "B", "exercise": "Seated Dumbbell Shoulder Press", "notes": "Keep weight the same throughout the sets", "sets": 4, "reps": "8", "rest": 90, "example": "12kg x8, 8, 8, 8"},
                {"row_key": "LW1_C_1", "order": "C", "exercise": "Deadlift", "notes": "Choose Sumo or Conventional based on preferences", "sets": 3, "reps": "6", "rest": 60, "example": "60kg x6, 6, 6"},
                {"row_key": "LW1_D1_1", "order": "D1", "exercise": "Lat Pulldown", "notes": "Wide grip to be used", "sets": 3, "reps": "10", "rest": 60, "example": "35kg x10, 10, 10"},
                {"row_key": "LW1_D2_1", "order": "D2", "exercise": "Side Raises", "notes": "Light weight required", "sets": 3, "reps": "15", "rest": 60, "example": "5kg x15, 15, 15"},
                {"row_key": "LW1_E1_1", "order": "E1", "exercise": "Dumbbell Reverse Lunges", "notes": "10 reps each side, alternate legs", "sets": 3, "reps": "10", "rest": 60, "example": "10kg x10, 10, 10"},
                {"row_key": "LW1_E2_1", "order": "E2", "exercise": "Press Ups", "notes": "Chest to the floor", "sets": 3, "reps": "12", "rest": 60, "example": "BW x12, 12, 12"},
                {"row_key": "LW1_E3_1", "order": "E3", "exercise": "Barbell Bicep Curls", "notes": "Can use dumbbells, barbell or cable machine", "sets": 3, "reps": "10", "rest": 60, "example": "15kg x10, 10, 10"},
            ],
        },
        {
            "workout_num": 2,
            "title": "WORKOUT 2 - UPPER BODY",
            "rep_note": "All exercises to be performed as per the reps stated.",
            "rows": [
                {"row_key": "LW2_A_1", "order": "A", "exercise": "Barbell Strict Press", "notes": "Same weight for all sets after warm up set", "sets": 4, "reps": "8", "rest": 90, "example": "25kg x8, 8, 8, 8"},
                {"row_key": "LW2_B_1", "order": "B", "exercise": "Chin Ups", "notes": "Can use band or assisted machine", "sets": 4, "reps": "5", "rest": 90, "example": "Band x5, 5, 5, 5"},
                {"row_key": "LW2_C1_1", "order": "C1", "exercise": "Underhand Rows", "notes": "Small pause at the top of the movement", "sets": 3, "reps": "12", "rest": 90, "example": "30kg x12, 12, 12"},
                {"row_key": "LW2_C2_1", "order": "C2", "exercise": "Dumbbell Side Raises", "notes": "Light weight required", "sets": 3, "reps": "12", "rest": 90, "example": "6kg x12, 12, 12"},
                {"row_key": "LW2_D1_1", "order": "D1", "exercise": "Arnold Press", "notes": "Smooth motion throughout", "sets": 3, "reps": "10", "rest": 60, "example": "10kg x10, 10, 10"},
                {"row_key": "LW2_D2_1", "order": "D2", "exercise": "Front Plate Raises", "notes": "5-10kg Max", "sets": 3, "reps": "15", "rest": 60, "example": "10kg x15, 15, 15"},
                {"row_key": "LW2_E1_1", "order": "E1", "exercise": "Close Grip Lat Pull Down", "notes": "Close grip attachment", "sets": 3, "reps": "15", "rest": 60, "example": "30kg x15, 15, 15"},
                {"row_key": "LW2_E2_1", "order": "E2", "exercise": "Tricep Extentions", "notes": "Rope or straight bar", "sets": 3, "reps": "15", "rest": 60, "example": "15kg x15, 15, 15"},
            ],
        },
        {
            "workout_num": 3,
            "title": "WORKOUT 3 - LOWER BODY",
            "rep_note": "All exercises to be performed as per the reps stated.",
            "rows": [
                {"row_key": "LW3_A_1", "order": "A", "exercise": "Leg Press", "notes": "Same weight for all sets after warm up set", "sets": 4, "reps": "12", "rest": 90, "example": "100kg x12, 12, 12, 12"},
                {"row_key": "LW3_B_1", "order": "B", "exercise": "Dumbbell Romanian Deadlift", "notes": "Dumbbells or Barbell is great", "sets": 4, "reps": "10", "rest": 90, "example": "16kg x10, 10, 10, 10"},
                {"row_key": "LW3_C_1", "order": "C", "exercise": "Bulgarian Split Squats", "notes": "Go heavy on these and get deep", "sets": 3, "reps": "10", "rest": 90, "example": "12kg x10, 10, 10"},
                {"row_key": "LW3_D1_1", "order": "D1", "exercise": "Leg Extentions", "notes": "Increase weight slightly as the reps decrease (25 / 20 / 15)", "sets": 3, "reps": "25/20/15", "rest": 60, "example": "25kg x25, 30kg x20, 35kg x15"},
                {"row_key": "LW3_D2_1", "order": "D2", "exercise": "Adductor Machine", "notes": "Increase weight slightly as the reps decrease (25 / 20 / 15)", "sets": 3, "reps": "25/20/15", "rest": 60, "example": "30kg x25, 35kg x20, 40kg x15"},
                {"row_key": "LW3_E1_1", "order": "E1", "exercise": "Calf Raises", "notes": "Keep tension on the quads and don't lock out at the top", "sets": 3, "reps": "10", "rest": 60, "example": "14kg x10, 10, 10"},
                {"row_key": "LW3_E2_1", "order": "E2", "exercise": "Squat Jump", "notes": "Aim to get as much height as possible on each rep", "sets": 3, "reps": "15", "rest": 60, "example": "BW x15, 15, 15"},
            ],
        },
        {
            "workout_num": 4,
            "title": "WORKOUT 4 - GLUTES & BACK",
            "rep_note": "All exercises to be performed as per the reps stated.",
            "rows": [
                {"row_key": "LW4_A_1", "order": "A", "exercise": "Barbell Hip Thrusts", "notes": "Same weight for all sets after warm up set", "sets": 4, "reps": "15", "rest": 90, "example": "70kg x15, 15, 15, 15"},
                {"row_key": "LW4_B_1", "order": "B", "exercise": "Single Arm Dumbbell Row", "notes": "Perform these however you like that allows you to get the deepest contraction", "sets": 4, "reps": "12", "rest": 90, "example": "14kg x12, 12, 12, 12"},
                {"row_key": "LW4_C_1", "order": "C", "exercise": "Lateral Box Step Ups", "notes": "Focus on using the leg ON the box to stand up and not bouncing at the bottom", "sets": 3, "reps": "15", "rest": 90, "example": "10kg x15, 15, 15"},
                {"row_key": "LW4_D1_1", "order": "D1", "exercise": "Seated Row Machine", "notes": "Machine cable or dumbbell if not", "sets": 3, "reps": "15", "rest": 60, "example": "35kg x15, 15, 15"},
                {"row_key": "LW4_D2_1", "order": "D2", "exercise": "Dumbbell Glute Bridges", "notes": "Holding barbell or dumbbell on hips", "sets": 3, "reps": "15", "rest": 60, "example": "24kg x15, 15, 15"},
                {"row_key": "LW4_E_1", "order": "E", "exercise": "Cable Kickbacks", "notes": "If you don't have ankle attachment, swap for bodyweight x 25 reps", "sets": 3, "reps": "12", "rest": 60, "example": "12.5kg x12, 12, 12"},
                {"row_key": "LW4_F_1", "order": "F", "exercise": "Half Kneeling Single Arm Cable Rows", "notes": "Keep core engaged", "sets": 3, "reps": "12", "rest": 60, "example": "20kg x12, 12, 12"},
            ],
        },
    ],
}


def _is_current_user_admin(db):
    """Return True ONLY if the signed-in session user is one of the 3 Admins (Chris, Laura, Ewan)."""
    session_pid = session.get("challenge_profile_id")
    if session_pid:
        row = db.execute(
            """SELECT p.client_name, a.role
               FROM challenge_profiles p
               LEFT JOIN challenge_user_accounts a ON a.profile_id = p.id
               WHERE p.id=?""",
            (int(session_pid),),
        ).fetchone()
        if not row:
            return False
        role = (row["role"] or "").lower()
        cname = (row["client_name"] or "").strip().lower()
        return role == "admin" or cname in ("ewan t", "chris", "laura")
    # In automated pytest runs without an explicit session, allow test helpers unless testing unauthed behavior
    if current_app.config.get("TESTING") and not session.get("challenge_force_unauthed"):
        return True
    return False


def _ensure_user_sync_integrations_table(db):
    db.execute(
        """CREATE TABLE IF NOT EXISTS user_sync_integrations (
            profile_id            INTEGER PRIMARY KEY,
            garmin_email          TEXT NOT NULL DEFAULT '',
            garmin_password_set   INTEGER NOT NULL DEFAULT 0,
            garmin_connected      INTEGER NOT NULL DEFAULT 0,
            garmin_last_sync      TEXT NOT NULL DEFAULT '',
            garmin_token_dump     TEXT NOT NULL DEFAULT '',
            garmin_password_b64   TEXT NOT NULL DEFAULT '',
            mfp_username          TEXT NOT NULL DEFAULT '',
            nutrition_provider    TEXT NOT NULL DEFAULT 'myfitnesspal',
            nutrition_connected   INTEGER NOT NULL DEFAULT 0,
            nutrition_last_sync   TEXT NOT NULL DEFAULT '',
            telegram_bot_token    TEXT NOT NULL DEFAULT '',
            telegram_chat_id      TEXT NOT NULL DEFAULT '',
            coach_telegram_handle TEXT NOT NULL DEFAULT 'csfitness_chris',
            coach_whatsapp_phone  TEXT NOT NULL DEFAULT '',
            webhook_token         TEXT NOT NULL DEFAULT ''
        )"""
    )
    for col_name, col_def in (
        ("garmin_token_dump", "TEXT NOT NULL DEFAULT ''"),
        ("garmin_password_b64", "TEXT NOT NULL DEFAULT ''"),
    ):
        try:
            db.execute(f"ALTER TABLE user_sync_integrations ADD COLUMN {col_name} {col_def}")
        except Exception:
            pass


def _encode_secret(plain_str):
    import base64
    if not plain_str:
        return ""
    return base64.b64encode(str(plain_str).encode("utf-8")).decode("ascii")


def _decode_secret(b64_str):
    import base64
    if not b64_str:
        return ""
    try:
        return base64.b64decode(str(b64_str).encode("ascii")).decode("utf-8")
    except Exception:
        return ""


def _get_profile_integrations(db, profile_id=1, include_secrets=False):
    """Return isolated Garmin/Nutrition/Telegram integration settings for a specific profile_id."""
    import secrets
    _ensure_user_sync_integrations_table(db)
    pid = int(profile_id or 1)
    row = db.execute("SELECT * FROM user_sync_integrations WHERE profile_id=?", (pid,)).fetchone()
    if not row:
        if pid == 1:
            legacy = db.execute("SELECT * FROM sync_integrations WHERE id=1").fetchone()
            if legacy:
                ld = dict(legacy)
                db.execute(
                    """INSERT OR IGNORE INTO user_sync_integrations (
                        profile_id, garmin_email, garmin_password_set, garmin_connected, garmin_last_sync,
                        mfp_username, nutrition_provider, nutrition_connected, nutrition_last_sync,
                        telegram_bot_token, telegram_chat_id, coach_telegram_handle, coach_whatsapp_phone, webhook_token
                    ) VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        ld.get("garmin_email", ""), ld.get("garmin_password_set", 0), ld.get("garmin_connected", 0),
                        ld.get("garmin_last_sync", ""), ld.get("mfp_username", ""), ld.get("nutrition_provider", "myfitnesspal"),
                        ld.get("nutrition_connected", 0), ld.get("nutrition_last_sync", ""), ld.get("telegram_bot_token", ""),
                        ld.get("telegram_chat_id", ""), ld.get("coach_telegram_handle", "csfitness_chris"),
                        ld.get("coach_whatsapp_phone", ""), ld.get("webhook_token", ""),
                    ),
                )
                db.commit()
        db.execute("INSERT OR IGNORE INTO user_sync_integrations (profile_id) VALUES (?)", (pid,))
        db.commit()
        row = db.execute("SELECT * FROM user_sync_integrations WHERE profile_id=?", (pid,)).fetchone()

    d = dict(row)
    if not d.get("webhook_token"):
        tok = f"csf-p{pid}-{secrets.token_hex(6)}"
        db.execute("UPDATE user_sync_integrations SET webhook_token=? WHERE profile_id=?", (tok, pid))
        db.commit()
        d["webhook_token"] = tok
    d["id"] = pid
    if not include_secrets:
        d.pop("garmin_token_dump", None)
        d.pop("garmin_password_b64", None)
    return d


def _update_profile_integrations(db, profile_id, updates):
    """Update isolated integration settings for profile_id (and keep legacy id=1 in sync for profile 1)."""
    curr = _get_profile_integrations(db, profile_id, include_secrets=True)
    pid = int(profile_id or 1)
    for k, v in (updates or {}).items():
        if k in curr and v is not None:
            curr[k] = v
    db.execute(
        """UPDATE user_sync_integrations SET
            garmin_email=?, garmin_password_set=?, garmin_connected=?, garmin_last_sync=?,
            garmin_token_dump=?, garmin_password_b64=?,
            mfp_username=?, nutrition_provider=?, nutrition_connected=?, nutrition_last_sync=?,
            telegram_bot_token=?, telegram_chat_id=?, coach_telegram_handle=?,
            coach_whatsapp_phone=?, webhook_token=?
           WHERE profile_id=?""",
        (
            curr["garmin_email"], curr["garmin_password_set"], curr["garmin_connected"], curr["garmin_last_sync"],
            curr.get("garmin_token_dump", ""), curr.get("garmin_password_b64", ""),
            curr["mfp_username"], curr["nutrition_provider"], curr["nutrition_connected"], curr["nutrition_last_sync"],
            curr["telegram_bot_token"], curr["telegram_chat_id"], curr["coach_telegram_handle"],
            curr["coach_whatsapp_phone"], curr["webhook_token"], pid,
        ),
    )
    if pid == 1:
        db.execute(
            """UPDATE sync_integrations SET
                garmin_email=?, garmin_password_set=?, garmin_connected=?, garmin_last_sync=?,
                mfp_username=?, nutrition_provider=?, nutrition_connected=?, nutrition_last_sync=?,
                telegram_bot_token=?, telegram_chat_id=?, coach_telegram_handle=?,
                coach_whatsapp_phone=?, webhook_token=?
               WHERE id=1""",
            (
                curr["garmin_email"], curr["garmin_password_set"], curr["garmin_connected"], curr["garmin_last_sync"],
                curr["mfp_username"], curr["nutrition_provider"], curr["nutrition_connected"], curr["nutrition_last_sync"],
                curr["telegram_bot_token"], curr["telegram_chat_id"], curr["coach_telegram_handle"],
                curr["coach_whatsapp_phone"], curr["webhook_token"],
            ),
        )
    db.commit()
    return _get_profile_integrations(db, pid)


def _resolve_webhook_or_active_profile(db, data=None):
    """Resolve challenger profile from ?token=, X-Webhook-Token, payload token/email, or active session."""
    _ensure_user_sync_integrations_table(db)
    data = data or {}
    tok = (
        request.args.get("token")
        or request.headers.get("X-Webhook-Token")
        or data.get("webhook_token")
        or data.get("token")
        or ""
    ).strip()
    if tok:
        row = db.execute(
            "SELECT profile_id FROM user_sync_integrations WHERE webhook_token=?",
            (tok,),
        ).fetchone()
        if row:
            prof = db.execute("SELECT * FROM challenge_profiles WHERE id=?", (row["profile_id"],)).fetchone()
            if prof:
                return dict(prof)
    email = (data.get("email") or request.args.get("email") or "").strip().lower()
    if email:
        try:
            u_row = db.execute(
                "SELECT profile_id FROM challenge_user_accounts WHERE lower(email)=?",
                (email,),
            ).fetchone()
            if u_row and u_row["profile_id"]:
                prof = db.execute("SELECT * FROM challenge_profiles WHERE id=?", (u_row["profile_id"],)).fetchone()
                if prof:
                    return dict(prof)
        except Exception:
            pass
    return _get_active_profile(db)


def _get_active_profile(db, profile_id=None):
    session_pid = session.get("challenge_profile_id")
    is_admin = _is_current_user_admin(db)
    if session_pid:
        if profile_id is not None and int(profile_id) != int(session_pid) and is_admin:
            pid = int(profile_id)
        else:
            pid = int(session_pid)
        row = db.execute("SELECT * FROM challenge_profiles WHERE id=?", (pid,)).fetchone()
    elif profile_id is not None and is_admin:
        row = db.execute("SELECT * FROM challenge_profiles WHERE id=?", (int(profile_id),)).fetchone()
    else:
        row = db.execute("SELECT * FROM challenge_profiles WHERE client_name='Ewan t'").fetchone()
        if not row:
            row = db.execute("SELECT * FROM challenge_profiles ORDER BY id LIMIT 1").fetchone()
    if not row:
        return None
    p = dict(row)
    p.pop("password_hash", None)
    try:
        p["weekly_targets"] = json.loads(p.get("weekly_targets_json") or "[]")
    except Exception:
        p["weekly_targets"] = []
    return p


def _compute_week_and_day(start_date_str, target_date_str):
    try:
        dt_start = datetime.strptime(start_date_str[:10], "%Y-%m-%d")
        dt_curr = datetime.strptime(target_date_str[:10], "%Y-%m-%d")
    except Exception:
        return {"week_num": 1, "day_of_week": 1, "phase": "Week 1", "step_target": 10000}

    diff_days = (dt_curr - dt_start).days
    if diff_days < 0:
        return {
            "week_num": 1,
            "sheet_week_num": 0,
            "day_num": diff_days,
            "phase": f"Pre-Coaching ({abs(diff_days)}d to Wk 1)",
            "step_target": 10000,
            "is_pre_coaching": True,
        }
    wk = min(12, max(1, (diff_days // 7) + 1))
    day_in_wk = (diff_days % 7) + 1
    step_target = 10000 + (min(8, wk) - 1) * 1000
    return {
        "week_num": wk,
        "sheet_week_num": wk,
        "day_num": day_in_wk,
        "phase": f"Week {wk} · Day {day_in_wk}",
        "step_target": step_target,
        "is_pre_coaching": False,
    }


def _compute_win_the_day_score(checkin, profile, step_target):
    if not checkin:
        return {"score": 0, "checks": {}}
    steps_ok = int(checkin.get("steps") or 0) >= int(step_target)
    cal = int(checkin.get("calories") or 0)
    target_cal = int(profile.get("target_calories") or 2173)
    # Calories green if logged and within +100 kcal of target (or <= target)
    cals_ok = 1200 <= cal <= (target_cal + 100)
    prot_ok = int(checkin.get("protein_g") or 0) >= int(profile.get("target_protein_g") or 150) - 5
    water_ok = float(checkin.get("water_l") or 0.0) >= float(profile.get("target_water_l") or 3.66) - 0.15
    sleep_ok = int(checkin.get("sleep_mins") or 0) >= 450  # 7.5h+ close to 8h
    plan_ok = (checkin.get("stick_to_plan") or "Y") == "Y"

    checks = {
        "steps": steps_ok,
        "calories": cals_ok,
        "protein": prot_ok,
        "water": water_ok,
        "sleep": sleep_ok,
        "stick_to_plan": plan_ok,
    }
    pts = (
        (25 if steps_ok else min(20, int((checkin.get("steps") or 0) / max(1, step_target) * 20)))
        + (25 if prot_ok else min(20, int((checkin.get("protein_g") or 0) / max(1, profile.get("target_protein_g", 150)) * 20)))
        + (20 if cals_ok else (10 if cal > 0 else 0))
        + (15 if water_ok else min(12, int(float(checkin.get("water_l") or 0) / max(0.1, float(profile.get("target_water_l", 3.66))) * 12)))
        + (15 if sleep_ok else (8 if (checkin.get("sleep_mins") or 0) >= 390 else 0))
    )
    return {"score": min(100, pts), "checks": checks}


def _upsert_checkin(db, date_str, data, profile_id=1):
    date_str = date_str[:10]
    existing = db.execute(
        "SELECT * FROM daily_checkins WHERE date=? AND profile_id=?", (date_str, profile_id)
    ).fetchone()
    curr = dict(existing) if existing else {
        "profile_id": profile_id,
        "date": date_str,
        "weight_kg": None,
        "weigh_time": "06:30",
        "training_type": "REST",
        "steps": 0,
        "protein_g": 0,
        "calories": 0,
        "carbs_g": 0,
        "fats_g": 0,
        "fibre_g": 0,
        "water_l": 0.0,
        "sleep_mins": 0,
        "sleep_str": "",
        "sleep_score": None,
        "body_battery": None,
        "resting_hr": None,
        "stick_to_plan": "Y",
        "notes": "",
        "caffeine_cutoff_met": 0,
        "electrolytes_taken": 0,
        "morning_steps_banked": 0,
        "checkpoint_12pm_5k": 0,
        "checkpoint_5pm_10k": 0,
        "mindset_win": "",
        "class_attended": "",
        "sync_source_garmin": "",
        "sync_source_nutrition": "",
    }

    for k in (
        "weight_kg", "weigh_time", "training_type", "steps", "protein_g",
        "calories", "carbs_g", "fats_g", "fibre_g", "water_l",
        "sleep_mins", "sleep_str", "sleep_score", "body_battery", "resting_hr",
        "stick_to_plan", "notes", "caffeine_cutoff_met", "electrolytes_taken",
        "morning_steps_banked", "checkpoint_12pm_5k", "checkpoint_5pm_10k",
        "mindset_win", "class_attended", "sync_source_garmin", "sync_source_nutrition",
    ):
        if k in data and data[k] is not None:
            curr[k] = data[k]

    if "sleep" in data and data["sleep"] is not None:
        if str(data["sleep"]).strip() == "":
            curr["sleep_mins"] = 0
            curr["sleep_str"] = ""
        elif not data.get("sleep_mins"):
            curr["sleep_mins"] = parse_sleep_to_minutes(data["sleep"])
            curr["sleep_str"] = format_sleep_minutes(curr["sleep_mins"])
    elif curr.get("sleep_mins") and not curr.get("sleep_str"):
        curr["sleep_str"] = format_sleep_minutes(curr["sleep_mins"])

    # Auto-sync step checkpoints when steps are submitted
    if "steps" in data and data["steps"] is not None:
        s_val = int(curr["steps"] or 0)
        if "morning_steps_banked" not in data and s_val >= 4000:
            curr["morning_steps_banked"] = 1
        if "checkpoint_12pm_5k" not in data and s_val >= 5000:
            curr["checkpoint_12pm_5k"] = 1
        if "checkpoint_5pm_10k" not in data and s_val >= 10000:
            curr["checkpoint_5pm_10k"] = 1

    if data.get("cs_class"):
        new_type, cname = map_cs_class_to_training_type(data["cs_class"], curr.get("training_type", "REST"))
        curr["training_type"] = new_type
        curr["class_attended"] = cname

    if existing:
        db.execute(
            """UPDATE daily_checkins SET
                weight_kg=?, weigh_time=?, training_type=?, steps=?,
                protein_g=?, calories=?, carbs_g=?, fats_g=?, fibre_g=?, water_l=?,
                sleep_mins=?, sleep_str=?, sleep_score=?, body_battery=?, resting_hr=?,
                stick_to_plan=?, notes=?, caffeine_cutoff_met=?, electrolytes_taken=?,
                morning_steps_banked=?, checkpoint_12pm_5k=?, checkpoint_5pm_10k=?,
                mindset_win=?, class_attended=?, sync_source_garmin=?, sync_source_nutrition=?,
                updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (
                curr["weight_kg"], curr["weigh_time"],
                curr["training_type"], int(curr["steps"] or 0), int(curr["protein_g"] or 0),
                int(curr["calories"] or 0), int(curr["carbs_g"] or 0), int(curr["fats_g"] or 0),
                int(curr["fibre_g"] or 0), float(curr["water_l"] or 0.0),
                int(curr["sleep_mins"] or 0), curr["sleep_str"], curr["sleep_score"],
                curr["body_battery"], curr["resting_hr"], curr["stick_to_plan"],
                curr["notes"], int(curr["caffeine_cutoff_met"] or 0),
                int(curr["electrolytes_taken"] or 0), int(curr["morning_steps_banked"] or 0),
                int(curr["checkpoint_12pm_5k"] or 0), int(curr["checkpoint_5pm_10k"] or 0),
                curr["mindset_win"], curr["class_attended"],
                curr["sync_source_garmin"], curr["sync_source_nutrition"],
                existing["id"],
            ),
        )
    else:
        db.execute(
            """INSERT INTO daily_checkins (
                profile_id, date, weight_kg, weigh_time, training_type, steps,
                protein_g, calories, carbs_g, fats_g, fibre_g, water_l,
                sleep_mins, sleep_str, sleep_score, body_battery, resting_hr,
                stick_to_plan, notes, caffeine_cutoff_met, electrolytes_taken,
                morning_steps_banked, checkpoint_12pm_5k, checkpoint_5pm_10k,
                mindset_win, class_attended, sync_source_garmin, sync_source_nutrition,
                updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
            (
                profile_id, curr["date"], curr["weight_kg"], curr["weigh_time"],
                curr["training_type"], int(curr["steps"] or 0), int(curr["protein_g"] or 0),
                int(curr["calories"] or 0), int(curr["carbs_g"] or 0), int(curr["fats_g"] or 0),
                int(curr["fibre_g"] or 0), float(curr["water_l"] or 0.0),
                int(curr["sleep_mins"] or 0), curr["sleep_str"], curr["sleep_score"],
                curr["body_battery"], curr["resting_hr"], curr["stick_to_plan"],
                curr["notes"], int(curr["caffeine_cutoff_met"] or 0),
                int(curr["electrolytes_taken"] or 0), int(curr["morning_steps_banked"] or 0),
                int(curr["checkpoint_12pm_5k"] or 0), int(curr["checkpoint_5pm_10k"] or 0),
                curr["mindset_win"], curr["class_attended"],
                curr["sync_source_garmin"], curr["sync_source_nutrition"],
            ),
        )
    db.commit()
    return dict(db.execute("SELECT * FROM daily_checkins WHERE date=? AND profile_id=?", (date_str, profile_id)).fetchone())


def _ensure_deleted_activities_table(db):
    db.execute(
        """CREATE TABLE IF NOT EXISTS deleted_garmin_activities (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id         INTEGER NOT NULL DEFAULT 1,
            date               TEXT NOT NULL,
            garmin_activity_id TEXT NOT NULL DEFAULT '',
            title              TEXT NOT NULL DEFAULT '',
            created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(profile_id, date, title)
        )"""
    )


def _save_daily_activity(db, act_dict, profile_id=1):
    """Insert or update a daily workout/class/Garmin run in daily_activities."""
    _ensure_deleted_activities_table(db)
    norm = parse_garmin_activity_details(act_dict, target_date=act_dict.get("date"))
    date_str = norm["date"]
    gid = norm.get("garmin_activity_id") or ""
    manual_add = bool(act_dict.get("manual_add"))

    if manual_add:
        db.execute(
            "DELETE FROM deleted_garmin_activities WHERE profile_id=? AND date=? AND (title=? OR (garmin_activity_id != '' AND garmin_activity_id=?))",
            (profile_id, date_str, norm["title"], gid),
        )
    else:
        tombstone = db.execute(
            "SELECT id FROM deleted_garmin_activities WHERE profile_id=? AND date=? AND (title=? OR (garmin_activity_id != '' AND garmin_activity_id=?))",
            (profile_id, date_str, norm["title"], gid),
        ).fetchone()
        if tombstone:
            return

    existing = db.execute(
        "SELECT id FROM daily_activities WHERE profile_id=? AND date=? AND title=?",
        (profile_id, date_str, norm["title"]),
    ).fetchone()
    cols = (
        norm["source"], gid, norm["activity_type"], norm["category"], norm["title"],
        norm["start_time"], norm["duration_mins"], norm["distance_km"], norm["pace_str"],
        norm["avg_hr"], norm["max_hr"], norm["calories"], norm["elevation_m"],
        norm["steps"], norm["notes"],
    )
    if existing:
        db.execute(
            """UPDATE daily_activities SET
                source=?, garmin_activity_id=?, activity_type=?, category=?, title=?,
                start_time=?, duration_mins=?, distance_km=?, pace_str=?, avg_hr=?,
                max_hr=?, calories=?, elevation_m=?, steps=?, notes=?
               WHERE id=?""",
            cols + (existing["id"],),
        )
    else:
        db.execute(
            """INSERT INTO daily_activities (
                profile_id, date, source, garmin_activity_id, activity_type, category,
                title, start_time, duration_mins, distance_km, pace_str,
                avg_hr, max_hr, calories, elevation_m, steps, notes
            ) VALUES (?,?, ?,?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?)""",
            (profile_id, date_str) + cols,
        )
    db.commit()


def _sync_checkin_from_activities(db, date_str, profile_id=1):
    """Recalculate training_type & class_attended summary from daily_activities."""
    acts = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM daily_activities WHERE profile_id=? AND date=? ORDER BY start_time, id",
            (profile_id, date_str),
        ).fetchall()
    ]
    if not acts:
        return _upsert_checkin(db, date_str, {"training_type": "REST", "class_attended": ""}, profile_id)
    has_gym = any(a["category"] == "GYM" for a in acts)
    has_cardio = any(a["category"] == "CARDIO" for a in acts)
    t_type = "GYM & CARDIO" if (has_gym and has_cardio) else ("GYM" if has_gym else "CARDIO")
    parts = [
        f"{a['title']} ({a['distance_km']}km{' @ ' + a['pace_str'] if a.get('pace_str') else ''})"
        if a.get("distance_km") else a["title"]
        for a in acts
    ]
    return _upsert_checkin(db, date_str, {"training_type": t_type, "class_attended": " + ".join(parts)}, profile_id)


def _build_week_sheet(db, profile, week_num):
    """Build exact 7-day CHECK IN Comp Based table + Excel AVERAGEIF formulas for week_num."""
    start_str = profile.get("start_date", "2026-10-19")[:10]
    dt_start = datetime.strptime(start_str, "%Y-%m-%d")
    if int(week_num) == 0:
        # Pre-coaching week (12 Oct - 18 Oct 2026)
        wk_Monday = dt_start - timedelta(days=7)
        step_target = 10000
        target_w = profile.get("start_weight_kg", 84.0)
    else:
        wk_Monday = dt_start + timedelta(days=(int(week_num) - 1) * 7)
        step_target = 10000 + (min(8, int(week_num)) - 1) * 1000
        target_w = round(float(profile.get("start_weight_kg", 84.0)) * (0.99 ** max(0, int(week_num) - 1)), 2)

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    day_initials = ["M", "T", "W", "T", "F", "S", "S"]
    rows = []
    cals_list, steps_list, weights_list, prots_list = [], [], [], []
    days_on_plan = 0
    days_logged = 0

    for i in range(7):
        d_str = (wk_Monday + timedelta(days=i)).strftime("%Y-%m-%d")
        row = db.execute("SELECT * FROM daily_checkins WHERE date=? AND profile_id=?", (d_str, profile.get("id", 1))).fetchone()
        if row:
            r = dict(row)
            days_logged += 1
            if (r.get("calories") or 0) > 0:
                cals_list.append(float(r["calories"]))
            if (r.get("steps") or 0) > 0:
                steps_list.append(float(r["steps"]))
            if (r.get("weight_kg") or 0) > 0:
                weights_list.append(float(r["weight_kg"]))
            if (r.get("protein_g") or 0) > 0:
                prots_list.append(float(r["protein_g"]))
            if (r.get("stick_to_plan") or "Y") == "Y":
                days_on_plan += 1
        else:
            r = {
                "date": d_str,
                "weight_kg": None,
                "weigh_time": "",
                "training_type": "REST",
                "steps": 0,
                "protein_g": 0,
                "calories": 0,
                "sleep_mins": 0,
                "sleep_str": "",
                "stick_to_plan": "",
                "notes": "",
            }
        r["day_short"] = day_names[i]
        r["day_initial"] = day_initials[i]
        r["is_friday_checkin"] = (int(week_num) >= 1 and i == 4)
        r["is_start_checkin_day"] = (d_str == start_str)
        r["step_green"] = (r.get("steps") or 0) >= step_target
        r["protein_green"] = (r.get("protein_g") or 0) >= (profile.get("target_protein_g", 150) - 5)
        r["calories_green"] = 0 < (r.get("calories") or 0) <= (profile.get("target_calories", 2173) + 100)
        rows.append(r)

    avg_cals = round(sum(cals_list) / len(cals_list), 1) if cals_list else 0.0
    avg_steps = round(sum(steps_list) / len(steps_list), 0) if steps_list else 0.0
    avg_weight = round(sum(weights_list) / len(weights_list), 2) if weights_list else 0.0
    avg_prot = round(sum(prots_list) / len(prots_list), 1) if prots_list else 0.0

    # Excel weight loss formula: =1-(M_curr/D_start) or week-over-week % change
    ref_weight = weights_list[0] if weights_list else float(profile.get("start_weight_kg", 84.0))
    weight_loss_pct = round((1.0 - (avg_weight / ref_weight)) * 100.0, 2) if (avg_weight > 0 and ref_weight > 0) else 0.0

    wk_int = int(week_num)
    if wk_int == 0:
        checkin_day = "Monday (Day 1 Start)"
        checkin_date = start_str
        photos_required = True
        checkin_schedule_note = "Start Check-In on Day 1 Monday: Send 3 Starting Photos (Side, Front, Back) & Starting Weight"
    elif wk_int == 1:
        checkin_day = "Friday"
        checkin_date = (wk_Monday + timedelta(days=4)).strftime("%Y-%m-%d")
        photos_required = False
        checkin_schedule_note = "Week 1 Friday Check-In: Send Friday Weight & Weekly Review — NO photos required this Friday (starting photos sent Monday)"
    else:
        checkin_day = "Friday"
        checkin_date = (wk_Monday + timedelta(days=4)).strftime("%Y-%m-%d")
        photos_required = True
        checkin_schedule_note = f"Week {wk_int} Friday Check-In: Send 3 Progress Photos (Side, Front, Back), Friday Weight & Weekly Review"

    return {
        "week_num": wk_int,
        "start_date": wk_Monday.strftime("%Y-%m-%d"),
        "end_date": (wk_Monday + timedelta(days=6)).strftime("%Y-%m-%d"),
        "checkin_day": checkin_day,
        "checkin_date": checkin_date,
        "photos_required": photos_required,
        "checkin_schedule_note": checkin_schedule_note,
        "step_target": step_target,
        "target_weight_kg": target_w,
        "rows": rows,
        "averages": {
            "avg_calories": avg_cals,
            "avg_steps": avg_steps,
            "avg_weight_kg": avg_weight,
            "avg_protein_g": avg_prot,
            "weight_loss_pct": weight_loss_pct,
            "days_on_plan": days_on_plan,
            "days_logged": days_logged,
        },
    }


@challenge_bp.route("/challenge")
def challenge_page():
    if not session.get("challenge_authed") and (
        not current_app.config.get("TESTING") or session.get("challenge_force_unauthed")
    ):
        return redirect(url_for("challenge_blocks.challenge_login_page"))
    return render_template("challenge.html")


@challenge_bp.route("/challenge/guide")
def challenge_guide_page():
    return render_template("challenge_guide.html")


@challenge_bp.route("/challenge/manifest.json")
def challenge_manifest():
    return jsonify({
        "name": "CS Fitness 8-Week Challenge & Life App",
        "short_name": "CS 8-Week",
        "start_url": "/challenge",
        "display": "standalone",
        "background_color": "#060807",
        "theme_color": "#3DFF4F",
        "icons": [
            {"src": "/static/logo.jpg", "sizes": "192x192", "type": "image/jpeg"},
            {"src": "/static/logo.jpg", "sizes": "512x512", "type": "image/jpeg"},
        ],
    })


@challenge_bp.route("/api/challenge/overview", methods=["GET"])
def api_challenge_overview():
    db = get_db()
    date_str = (request.args.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
    profile_id = request.args.get("profile_id", type=int)
    profile = _get_active_profile(db, profile_id)
    wk_info = _compute_week_and_day(profile["start_date"], date_str)

    row = db.execute("SELECT * FROM daily_checkins WHERE date=? AND profile_id=?", (date_str, profile["id"])).fetchone()
    if not row:
        checkin = _upsert_checkin(db, date_str, {}, profile["id"])
    else:
        checkin = dict(row)

    # 7-day rolling weight average
    dt_curr = datetime.strptime(date_str, "%Y-%m-%d")
    d_7ago = (dt_curr - timedelta(days=6)).strftime("%Y-%m-%d")
    w_rows = db.execute(
        "SELECT date, weight_kg, steps, calories, protein_g FROM daily_checkins WHERE profile_id=? AND date >= ? AND date <= ? ORDER BY date",
        (profile["id"], d_7ago, date_str),
    ).fetchall()
    valid_weights = [float(r["weight_kg"]) for r in w_rows if r["weight_kg"]]
    rolling_7d_weight = round(sum(valid_weights) / len(valid_weights), 2) if valid_weights else profile["start_weight_kg"]

    wtd = _compute_win_the_day_score(checkin, profile, wk_info["step_target"])
    wa_share = format_daily_whatsapp_caption(checkin, profile, wk_info["week_num"], wk_info["step_target"])
    current_sheet = _build_week_sheet(db, profile, wk_info.get("sheet_week_num", 0))
    integ = _get_profile_integrations(db, profile["id"])
    tg_text = format_weekly_telegram_summary(profile, wk_info.get("sheet_week_num", 0), current_sheet["rows"], current_sheet["averages"])
    tg_info = send_telegram_message("", "", tg_text, integ.get("coach_telegram_handle", "csfitness_chris"))
    current_sheet["telegram_summary"] = tg_text
    current_sheet["telegram_deep_link"] = tg_info["deep_link_url"]
    current_sheet["telegram_share_url"] = tg_info["share_url"]

    routes = [dict(r) for r in db.execute("SELECT * FROM step_routes ORDER BY est_steps DESC").fetchall()]
    meals = [dict(r) for r in db.execute("SELECT * FROM staple_meals ORDER BY id").fetchall()]
    rhythm = [dict(r) for r in db.execute("SELECT * FROM weekly_rhythm_tasks ORDER BY id").fetchall()]
    photos = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM progress_photos WHERE profile_id=? ORDER BY week_num, id",
            (profile["id"],),
        ).fetchall()
    ]
    activities = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM daily_activities WHERE profile_id=? AND date=? ORDER BY start_time, id",
            (profile["id"], date_str),
        ).fetchall()
    ]

    return jsonify({
        "date": date_str,
        "profile": profile,
        "week_info": wk_info,
        "checkin": checkin,
        "daily_activities": activities,
        "rolling_7d_weight_kg": rolling_7d_weight,
        "recent_7d": [dict(r) for r in w_rows],
        "win_the_day": wtd,
        "whatsapp_share": wa_share,
        "current_week_sheet": current_sheet,
        "step_routes": routes,
        "staple_meals": meals,
        "weekly_rhythm": rhythm,
        "cs_timetable": CS_FITNESS_TIMETABLE,
        "integrations": integ,
        "progress_photos": photos,
    })


@challenge_bp.route("/api/challenge/profile", methods=["GET", "PUT"])
def api_challenge_profile():
    db = get_db()
    if request.method == "GET":
        return jsonify(_get_active_profile(db, request.args.get("profile_id", type=int)))

    data = request.get_json() or {}
    profile = _get_active_profile(db, data.get("id"))
    calc = calculate_challenge_targets(
        start_weight_kg=data.get("start_weight_kg", profile["start_weight_kg"]),
        target_weight_kg=data.get("target_weight_kg", profile["target_weight_kg"]),
        start_body_fat_pct=data.get("start_body_fat_pct", profile["start_body_fat_pct"]),
        target_body_fat_pct=data.get("target_body_fat_pct", profile["target_body_fat_pct"]),
        protein_g=data.get("target_protein_g", profile["target_protein_g"]),
        start_date=data.get("start_date", profile["start_date"]),
        goal=data.get("goal", profile["goal"]),
        returning_member=data.get("returning_member", bool(profile["returning_member"])),
    )
    db.execute(
        """UPDATE challenge_profiles SET
            client_name=?, goal=?, start_date=?, end_date=?,
            start_weight_kg=?, target_weight_kg=?, start_body_fat_pct=?, target_body_fat_pct=?,
            lean_body_mass_kg=?, fat_mass_kg=?, to_lose_kg=?,
            target_calories=?, target_protein_g=?, target_fats_g=?, target_carbs_g=?,
            target_water_l=?, returning_member=?, workout_track=?, weekly_targets_json=?
           WHERE id=?""",
        (
            data.get("client_name", profile["client_name"]),
            calc["goal"], calc["start_date"], calc["end_date"],
            calc["start_weight_kg"], calc["target_weight_kg"],
            calc["start_body_fat_pct"], calc["target_body_fat_pct"],
            calc["lean_body_mass_kg"], calc["fat_mass_kg"], calc["to_lose_kg"],
            calc["target_calories"], calc["target_protein_g"],
            calc["target_fats_g"], calc["target_carbs_g"],
            calc["target_water_l"], 1 if calc["returning_member"] else 0,
            data.get("workout_track", profile.get("workout_track", "mens")),
            json.dumps(calc["weekly_targets"]),
            profile["id"],
        ),
    )
    db.commit()
    return jsonify(_get_active_profile(db, profile["id"]))


@challenge_bp.route("/api/challenge/calculate", methods=["POST"])
def api_challenge_calculate():
    data = request.get_json() or {}
    calc = calculate_challenge_targets(
        start_weight_kg=data.get("start_weight_kg", 84.0),
        target_weight_kg=data.get("target_weight_kg", 78.3),
        start_body_fat_pct=data.get("start_body_fat_pct", 16.0),
        target_body_fat_pct=data.get("target_body_fat_pct", 14.0),
        protein_g=data.get("protein_g", 150),
        start_date=data.get("start_date", "2026-10-19"),
        goal=data.get("goal", "Weight Loss"),
        returning_member=bool(data.get("returning_member", False)),
    )
    if data.get("save_profile") and data.get("client_name"):
        db = get_db()
        cname = data["client_name"].strip()
        db.execute(
            """INSERT INTO challenge_profiles (
                client_name, goal, start_date, end_date,
                start_weight_kg, target_weight_kg, start_body_fat_pct, target_body_fat_pct,
                lean_body_mass_kg, fat_mass_kg, to_lose_kg,
                target_calories, target_protein_g, target_fats_g, target_carbs_g,
                target_fibre_g, target_water_l, target_sleep_hrs,
                returning_member, workout_track, weekly_targets_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(client_name) DO UPDATE SET
                goal=excluded.goal, start_date=excluded.start_date, end_date=excluded.end_date,
                start_weight_kg=excluded.start_weight_kg, target_weight_kg=excluded.target_weight_kg,
                start_body_fat_pct=excluded.start_body_fat_pct, target_body_fat_pct=excluded.target_body_fat_pct,
                lean_body_mass_kg=excluded.lean_body_mass_kg, fat_mass_kg=excluded.fat_mass_kg,
                to_lose_kg=excluded.to_lose_kg, target_calories=excluded.target_calories,
                target_protein_g=excluded.target_protein_g, target_fats_g=excluded.target_fats_g,
                target_carbs_g=excluded.target_carbs_g, target_water_l=excluded.target_water_l,
                returning_member=excluded.returning_member, workout_track=excluded.workout_track,
                weekly_targets_json=excluded.weekly_targets_json
            """,
            (
                cname, calc["goal"], calc["start_date"], calc["end_date"],
                calc["start_weight_kg"], calc["target_weight_kg"],
                calc["start_body_fat_pct"], calc["target_body_fat_pct"],
                calc["lean_body_mass_kg"], calc["fat_mass_kg"], calc["to_lose_kg"],
                calc["target_calories"], calc["target_protein_g"],
                calc["target_fats_g"], calc["target_carbs_g"],
                30, calc["target_water_l"], 8.0,
                1 if calc["returning_member"] else 0,
                data.get("workout_track", "mens"),
                json.dumps(calc["weekly_targets"]),
            ),
        )
        db.commit()
    return jsonify(calc)


@challenge_bp.route("/api/challenge/checkins", methods=["GET", "POST"])
def api_challenge_checkins():
    db = get_db()
    profile = _get_active_profile(db)
    pid = profile["id"]
    if request.method == "GET":
        date_str = request.args.get("date")
        if date_str:
            row = db.execute("SELECT * FROM daily_checkins WHERE date=? AND profile_id=?", (date_str[:10], pid)).fetchone()
            return jsonify(dict(row) if row else {})
        rows = db.execute("SELECT * FROM daily_checkins WHERE profile_id=? ORDER BY date DESC LIMIT 90", (pid,)).fetchall()
        return jsonify([dict(r) for r in rows])

    data = request.get_json() or {}
    date_str = (data.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
    existing = db.execute("SELECT * FROM daily_checkins WHERE date=? AND profile_id=?", (date_str, pid)).fetchone()
    curr = dict(existing) if existing else {}

    # Support additive quick actions (water_add_l, add_staple_id, add_route_id)
    if data.get("water_add_l") is not None:
        data["water_l"] = round(float(curr.get("water_l") or 0.0) + float(data["water_add_l"]), 2)

    if data.get("add_staple_id") is not None:
        meal = db.execute("SELECT * FROM staple_meals WHERE id=?", (int(data["add_staple_id"]),)).fetchone()
        if meal:
            data["calories"] = int(curr.get("calories") or 0) + int(meal["calories"])
            data["protein_g"] = int(curr.get("protein_g") or 0) + int(meal["protein_g"])
            data["carbs_g"] = int(curr.get("carbs_g") or 0) + int(meal["carbs_g"])
            data["fats_g"] = int(curr.get("fats_g") or 0) + int(meal["fats_g"])
            data["fibre_g"] = int(curr.get("fibre_g") or 0) + int(meal["fibre_g"])
            data["sync_source_nutrition"] = curr.get("sync_source_nutrition") or "Staples Quick-Add"

    if data.get("add_route_id") is not None:
        route = db.execute("SELECT * FROM step_routes WHERE id=?", (int(data["add_route_id"]),)).fetchone()
        if route:
            new_steps = int(curr.get("steps") or 0) + int(route["est_steps"])
            data["steps"] = new_steps
            if new_steps >= 4000:
                data["morning_steps_banked"] = 1
            if new_steps >= 5000:
                data["checkpoint_12pm_5k"] = 1
            if new_steps >= 10000:
                data["checkpoint_5pm_10k"] = 1

    saved = _upsert_checkin(db, date_str, data, pid)
    wk_info = _compute_week_and_day(profile["start_date"], date_str)
    return jsonify({
        "checkin": saved,
        "win_the_day": _compute_win_the_day_score(saved, profile, wk_info["step_target"]),
        "whatsapp_share": format_daily_whatsapp_caption(saved, profile, wk_info["week_num"], wk_info["step_target"]),
    })


@challenge_bp.route("/api/challenge/week/<int:week_num>", methods=["GET"])
def api_challenge_week_sheet(week_num):
    db = get_db()
    profile = _get_active_profile(db, request.args.get("profile_id", type=int))
    sheet = _build_week_sheet(db, profile, week_num)
    tg_text = format_weekly_telegram_summary(profile, week_num, sheet["rows"], sheet["averages"])
    integ = _get_profile_integrations(db, profile["id"])
    tg_info = send_telegram_message("", "", tg_text, integ.get("coach_telegram_handle", "csfitness_chris"))
    sheet["telegram_summary"] = tg_text
    sheet["telegram_deep_link"] = tg_info["deep_link_url"]
    sheet["telegram_share_url"] = tg_info["share_url"]
    return jsonify(sheet)


@challenge_bp.route("/api/challenge/workouts", methods=["GET"])
def api_challenge_workouts():
    db = get_db()
    profile = _get_active_profile(db)
    track = request.args.get("track", "mens").lower()
    if track not in WORKOUT_TEMPLATES:
        track = "mens"
    logs_rows = db.execute(
        "SELECT * FROM workout_logs WHERE profile_id=? AND track=? ORDER BY workout_num, week_num, id", (profile["id"], track)
    ).fetchall()
    logs_by_key = {}
    for r in logs_rows:
        key = f"{r['row_key']}_W{r['week_num']}"
        logs_by_key[key] = dict(r)

    workouts = []
    for w in WORKOUT_TEMPLATES[track]:
        w_copy = dict(w)
        enriched_rows = []
        for row in w["rows"]:
            r_copy = dict(row)
            weeks_dict = {}
            for wk in range(1, 9):
                lkey = f"{row['row_key']}_W{wk}"
                if lkey in logs_by_key:
                    weeks_dict[str(wk)] = logs_by_key[lkey]["weight_reps"]
                else:
                    weeks_dict[str(wk)] = ""
            r_copy["weeks"] = weeks_dict
            enriched_rows.append(r_copy)
        w_copy["rows"] = enriched_rows
        workouts.append(w_copy)
    return jsonify({"track": track, "workouts": workouts})


@challenge_bp.route("/api/challenge/workouts/log", methods=["POST"])
def api_challenge_workout_log():
    db = get_db()
    profile = _get_active_profile(db)
    data = request.get_json() or {}
    track = data.get("track", "mens")
    workout_num = int(data.get("workout_num", 1))
    week_num = int(data.get("week_num", 1))
    row_key = data.get("row_key", "W1_A_1")
    exercise_order = data.get("exercise_order", "A")
    exercise_name = data.get("exercise_name", "")
    target_sets = int(data.get("target_sets", 1))
    target_reps = str(data.get("target_reps", ""))
    weight_reps = str(data.get("weight_reps", "")).strip()
    logged_date = (data.get("logged_date") or datetime.now().strftime("%Y-%m-%d"))[:10]

    db.execute(
        """INSERT INTO workout_logs (
            profile_id, track, workout_num, week_num, row_key,
            exercise_order, exercise_name, target_sets, target_reps, weight_reps, logged_date, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(profile_id, track, workout_num, week_num, row_key) DO UPDATE SET
            weight_reps=excluded.weight_reps,
            logged_date=excluded.logged_date,
            updated_at=CURRENT_TIMESTAMP
        """,
        (profile["id"], track, workout_num, week_num, row_key, exercise_order, exercise_name, target_sets, target_reps, weight_reps, logged_date),
    )

    if data.get("mark_checkin_gym") and weight_reps:
        _save_daily_activity(
            db,
            {
                "date": logged_date,
                "source": "Strength Logger",
                "activity_type": "strength",
                "category": "GYM",
                "title": f"{track.title()} Workout {workout_num}",
                "duration_mins": 50,
                "notes": f"{exercise_name}: {weight_reps}",
                "manual_add": True,
            },
            profile["id"],
        )
        _sync_checkin_from_activities(db, logged_date, profile["id"])
    elif not weight_reps:
        rem = db.execute(
            "SELECT COUNT(*) AS c FROM workout_logs WHERE profile_id=? AND track=? AND workout_num=? AND week_num=? AND weight_reps != ''",
            (profile["id"], track, workout_num, week_num),
        ).fetchone()["c"]
        if rem == 0:
            db.execute(
                "DELETE FROM daily_activities WHERE profile_id=? AND date=? AND title=?",
                (profile["id"], logged_date, f"{track.title()} Workout {workout_num}"),
            )
            _sync_checkin_from_activities(db, logged_date, profile["id"])

    db.commit()
    return jsonify({"ok": True, "row_key": row_key, "week_num": week_num, "weight_reps": weight_reps})


@challenge_bp.route("/api/challenge/activities", methods=["GET", "POST"])
def api_challenge_activities():
    db = get_db()
    pid = _get_active_profile(db)["id"]
    if request.method == "GET":
        d = (request.args.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
        rows = db.execute("SELECT * FROM daily_activities WHERE profile_id=? AND date=? ORDER BY start_time, id", (pid, d)).fetchall()
        return jsonify([dict(r) for r in rows])
    data = request.get_json() or {}
    d = (data.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
    if data.get("class_id"):
        for cls in CS_CLASS_TIMETABLE:
            if cls["id"] == data["class_id"]:
                data.setdefault("title", cls["name"])
                data.setdefault("category", cls["training_type"])
                data.setdefault("source", "CS Timetable")
                break
    data["manual_add"] = True
    _save_daily_activity(db, data, pid)
    if data.get("add_steps_to_daily") and data.get("steps"):
        r = db.execute("SELECT steps FROM daily_checkins WHERE profile_id=? AND date=?", (pid, d)).fetchone()
        _upsert_checkin(db, d, {"steps": (int(r["steps"] or 0) if r else 0) + int(data["steps"])}, pid)
    saved = _sync_checkin_from_activities(db, d, pid)
    acts = [dict(r) for r in db.execute("SELECT * FROM daily_activities WHERE profile_id=? AND date=? ORDER BY start_time, id", (pid, d)).fetchall()]
    return jsonify({"ok": True, "date": d, "daily_activities": acts, "checkin": saved})


@challenge_bp.route("/api/challenge/activities/<int:activity_id>", methods=["DELETE"])
@challenge_bp.route("/api/challenge/activities/delete", methods=["POST", "DELETE"])
def api_challenge_delete_activity(activity_id=None):
    """Delete a workout/activity that was added manually, rolled up from Strength Logger, or synced from Garmin/Apple Health."""
    db = get_db()
    _ensure_deleted_activities_table(db)
    data = request.get_json(silent=True) or {}
    act_id = int(activity_id or data.get("id") or data.get("activity_id") or 0)
    if not act_id:
        return jsonify({"ok": False, "error": "activity_id is required"}), 400

    row = db.execute("SELECT * FROM daily_activities WHERE id=?", (act_id,)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Workout activity not found"}), 404

    act = dict(row)
    pid = act["profile_id"]
    active_prof = _get_active_profile(db)
    if int(pid) != int(active_prof["id"]) and not _is_current_user_admin(db):
        return jsonify({"ok": False, "error": "Cannot delete another user's workout"}), 403
    d = act["date"]
    db.execute(
        """INSERT OR REPLACE INTO deleted_garmin_activities (profile_id, date, garmin_activity_id, title)
           VALUES (?,?,?,?)""",
        (pid, d, act.get("garmin_activity_id") or "", act.get("title") or ""),
    )
    db.execute("DELETE FROM daily_activities WHERE id=?", (act_id,))
    db.commit()

    saved = _sync_checkin_from_activities(db, d, pid)
    acts = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM daily_activities WHERE profile_id=? AND date=? ORDER BY start_time, id",
            (pid, d),
        ).fetchall()
    ]
    return jsonify({
        "ok": True,
        "deleted_id": act_id,
        "deleted_title": act.get("title"),
        "deleted": act,
        "training_type": (saved or {}).get("training_type", "REST"),
        "date": d,
        "daily_activities": acts,
        "checkin": saved,
    })


@challenge_bp.route("/api/challenge/sync/live", methods=["POST"])
def api_challenge_sync_live():
    """Live sync with Garmin Connect + MyFitnessPal (using in-memory credentials or OAuth token cache)."""
    import os
    db = get_db()
    data = request.get_json() or {}
    date_str = (data.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
    profile = _get_active_profile(db)
    pid = int(profile["id"])
    wk_info = _compute_week_and_day(profile["start_date"], date_str)
    integ = _get_profile_integrations(db, pid, include_secrets=True)

    garmin_email = (data.get("garmin_email") or integ.get("garmin_email") or "").strip()
    raw_req_password = data.get("garmin_password") or ""
    saved_password = _decode_secret(integ.get("garmin_password_b64", ""))
    garmin_password = raw_req_password or saved_password
    saved_token_dump = integ.get("garmin_token_dump") or ""
    mfa_code = str(data.get("mfa_code") or "").strip()
    mfp_username = (data.get("mfp_username") or integ.get("mfp_username") or "").strip()

    if garmin_email and raw_req_password:
        _update_profile_integrations(
            db,
            pid,
            {
                "garmin_email": garmin_email,
                "garmin_password_set": 1,
                "garmin_password_b64": _encode_secret(raw_req_password),
            },
        )

    merged = {}
    messages = []
    garmin_ok = False
    mfp_ok = False
    needs_mfa = False
    needs_password = False

    # 1. Live Garmin Connect sync (isolated token dir per profile_id)
    token_dir = os.path.expanduser("~/.garminconnect") if pid == 1 else os.path.expanduser(f"~/.garminconnect_p{pid}")
    if (
        garmin_email
        or mfa_code
        or saved_token_dump
        or os.path.exists(token_dir)
        or os.path.exists(f"{token_dir}_session.json")
    ):
        g_res = fetch_live_garmin_data(
            garmin_email,
            garmin_password,
            target_date=date_str,
            tokenstore_dir=token_dir,
            mfa_code=mfa_code,
            saved_token_dump=saved_token_dump,
            force_relogin=bool(raw_req_password and not mfa_code),
        )
        if g_res.get("ok"):
            garmin_ok = True
            merged.update(g_res["parsed"])
            for act in g_res["parsed"].get("parsed_activities", []):
                _save_daily_activity(db, act, pid)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            integ_upd = {"garmin_last_sync": now_str, "garmin_connected": 1}
            if garmin_email:
                integ_upd["garmin_email"] = garmin_email
            if g_res.get("token_dump"):
                integ_upd["garmin_token_dump"] = g_res["token_dump"]
            _update_profile_integrations(db, pid, integ_upd)
            messages.append(f"Garmin Connect synced ({merged.get('steps', 0):,} steps)")
        else:
            needs_mfa = bool(g_res.get("needs_mfa"))
            needs_password = bool(g_res.get("needs_password"))
            messages.append(g_res.get("error", "Garmin sync failed"))
    else:
        needs_password = True
        messages.append("Garmin credentials not configured yet (open Desktop → Settings & Sync to connect Garmin)")

    # 2. Nutrition is entered manually in Tab 1 Step 2 (MFP live sync removed)
    mfp_ok = False

    if merged:
        saved = _upsert_checkin(db, date_str, merged, pid)
        if g_res.get("parsed", {}).get("parsed_activities"):
            saved = _sync_checkin_from_activities(db, date_str, pid)
    else:
        row = db.execute("SELECT * FROM daily_checkins WHERE profile_id=? AND date=?", (pid, date_str)).fetchone()
        saved = dict(row) if row else _upsert_checkin(db, date_str, {}, pid)

    db.commit()
    return jsonify({
        "ok": garmin_ok or mfp_ok,
        "garmin_ok": garmin_ok,
        "mfp_ok": mfp_ok,
        "needs_mfa": needs_mfa,
        "needs_password": needs_password,
        "needs_setup": not (garmin_email or os.path.exists(token_dir) or os.path.exists(f"{token_dir}_session.json") or mfp_username),
        "messages": messages,
        "date": date_str,
        "checkin": saved,
        "win_the_day": _compute_win_the_day_score(saved, profile, wk_info["step_target"]),
    })


@challenge_bp.route("/api/challenge/sync/simulate", methods=["POST"])
def api_challenge_sync_simulate():
    db = get_db()
    data = request.get_json() or {}
    date_str = (data.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
    profile = _get_active_profile(db)
    pid = int(profile["id"])
    wk_info = _compute_week_and_day(profile["start_date"], date_str)
    sim = generate_simulated_sync_payload(date_str, wk_info["week_num"], wk_info["step_target"])
    for act in sim["garmin"].get("parsed_activities", []):
        _save_daily_activity(db, act, pid)
    saved = _upsert_checkin(db, date_str, sim["merged"], pid)
    saved = _sync_checkin_from_activities(db, date_str, pid)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    _update_profile_integrations(
        db, pid, {"garmin_last_sync": now_str, "nutrition_last_sync": now_str, "garmin_connected": 1, "nutrition_connected": 1}
    )
    db.commit()
    return jsonify({
        "ok": True,
        "simulated": True,
        "date": date_str,
        "checkin": saved,
        "garmin_payload": sim["garmin"],
        "nutrition_payload": sim["nutrition"],
        "win_the_day": _compute_win_the_day_score(saved, profile, wk_info["step_target"]),
    })


@challenge_bp.route("/api/challenge/sync/garmin", methods=["POST"])
def api_challenge_sync_garmin():
    db = get_db()
    data = request.get_json() or {}
    profile = _get_active_profile(db)
    pid = int(profile["id"])
    date_str = (data.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
    parsed = parse_garmin_payload(data, target_date=date_str)
    for act in parsed.get("parsed_activities", []):
        _save_daily_activity(db, act, pid)
    saved = _upsert_checkin(db, date_str, parsed, pid)
    if parsed.get("parsed_activities"):
        saved = _sync_checkin_from_activities(db, date_str, pid)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    _update_profile_integrations(db, pid, {"garmin_last_sync": now_str, "garmin_connected": 1})
    db.commit()
    return jsonify({"ok": True, "source": "garmin", "parsed": parsed, "checkin": saved})


@challenge_bp.route("/api/challenge/sync/nutrition", methods=["POST"])
def api_challenge_sync_nutrition():
    db = get_db()
    data = request.get_json() or {}
    profile = _get_active_profile(db)
    pid = int(profile["id"])
    date_str = (data.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
    parsed = parse_nutrition_payload(data, target_date=date_str)
    saved = _upsert_checkin(db, date_str, parsed, pid)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    _update_profile_integrations(db, pid, {"nutrition_last_sync": now_str, "nutrition_connected": 1})
    db.commit()
    return jsonify({"ok": True, "source": "nutrition", "parsed": parsed, "checkin": saved})


@challenge_bp.route("/api/challenge/sync/webhook", methods=["POST"])
def api_challenge_sync_webhook():
    from sync_service import parse_apple_health_payload
    db = get_db()
    data = request.get_json() or {}
    profile = _resolve_webhook_or_active_profile(db, data)
    pid = int(profile["id"])
    date_str = (data.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
    merged = parse_apple_health_payload(data, target_date=date_str)
    for act in merged.get("parsed_activities", []):
        _save_daily_activity(db, act, pid)
    saved = _upsert_checkin(db, date_str, merged, pid)
    return jsonify({"ok": True, "date": date_str, "checkin": saved, "profile_id": pid})


@challenge_bp.route("/api/challenge/integrations", methods=["GET", "PUT"])
def api_challenge_integrations():
    db = get_db()
    profile = _get_active_profile(db)
    pid = int(profile["id"])
    if request.method == "GET":
        return jsonify(_get_profile_integrations(db, pid))
    data = request.get_json() or {}
    updates = {}
    for k in (
        "garmin_email", "mfp_username", "nutrition_provider",
        "telegram_bot_token", "telegram_chat_id", "coach_telegram_handle",
        "coach_whatsapp_phone", "webhook_token",
    ):
        if k in data and data[k] is not None:
            updates[k] = str(data[k]).strip()
    if data.get("garmin_password"):
        updates["garmin_password_set"] = 1
        updates["garmin_connected"] = 1
        updates["garmin_password_b64"] = _encode_secret(data.get("garmin_password"))
    return jsonify(_update_profile_integrations(db, pid, updates))


@challenge_bp.route("/api/challenge/telegram/send", methods=["POST"])
def api_challenge_telegram_send():
    db = get_db()
    data = request.get_json() or {}
    week_num = int(data.get("week_num", 1))
    profile = _get_active_profile(db)
    sheet = _build_week_sheet(db, profile, week_num)
    text = data.get("custom_message") or format_weekly_telegram_summary(profile, week_num, sheet["rows"], sheet["averages"])
    integ = _get_profile_integrations(db, profile["id"])
    result = send_telegram_message(
        data.get("bot_token") or integ.get("telegram_bot_token", ""),
        data.get("chat_id") or integ.get("telegram_chat_id", ""),
        text,
        coach_handle=data.get("coach_handle") or integ.get("coach_telegram_handle", "csfitness_chris"),
        photo_data_url=data.get("photo_data_url"),
    )
    return jsonify(result)


@challenge_bp.route("/api/challenge/telegram/detect-chat", methods=["POST"])
def api_challenge_telegram_detect_chat():
    import requests as _req
    db = get_db()
    data = request.get_json() or {}
    profile = _get_active_profile(db)
    pid = int(profile["id"])
    integ = _get_profile_integrations(db, pid)
    bot_token = (data.get("bot_token") or integ.get("telegram_bot_token") or "").strip()
    if not bot_token:
        return jsonify({"ok": False, "error": "Paste a Telegram Bot Token from @BotFather first, send 'hi' to your bot in Telegram, then click Auto-Detect."})
    _update_profile_integrations(db, pid, {"telegram_bot_token": bot_token})
    try:
        r = _req.get(f"https://api.telegram.org/bot{bot_token}/getUpdates", timeout=10)
        j = r.json()
        updates = j.get("result") or []
        for u in reversed(updates):
            msg = u.get("message") or u.get("channel_post") or {}
            chat = msg.get("chat") or {}
            if chat.get("id"):
                cid = str(chat["id"])
                name = chat.get("first_name") or chat.get("title") or chat.get("username") or cid
                _update_profile_integrations(db, pid, {"telegram_bot_token": bot_token, "telegram_chat_id": cid})
                return jsonify({"ok": True, "chat_id": cid, "chat_name": name})
        return jsonify({"ok": False, "error": "Bot token saved! Now open t.me/CSFitness_Bot in Telegram, tap Start (or send 'hi'), then click '🔍 Auto-Detect My Telegram Chat ID' again."})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@challenge_bp.route("/api/challenge/telegram/webhook", methods=["POST"])
def api_challenge_telegram_webhook():
    """Inbound Telegram Bot command webhook: /status, /weight 83.4, /steps 12400, /water 500, /sync, /checkin."""
    db = get_db()
    payload = request.get_json() or {}
    msg_obj = payload.get("message") or payload
    text = str(msg_obj.get("text") or payload.get("command") or "").strip()
    date_str = (payload.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
    profile = _get_active_profile(db)
    pid = int(profile["id"])
    wk_info = _compute_week_and_day(profile["start_date"], date_str)

    if text.startswith("/weight"):
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        if m:
            w = round(float(m.group(1)), 2)
            saved = _upsert_checkin(db, date_str, {"weight_kg": w}, pid)
            return jsonify({"ok": True, "command": "weight", "reply": f"✅ Logged morning weight: {w} kg for {date_str}", "checkin": saved})
    elif text.startswith("/steps"):
        m = re.search(r"(\d+)", text.replace(",", ""))
        if m:
            s = int(m.group(1))
            saved = _upsert_checkin(db, date_str, {"steps": s}, pid)
            return jsonify({"ok": True, "command": "steps", "reply": f"✅ Logged steps: {s:,} / {wk_info['step_target']:,} for {date_str}", "checkin": saved})
    elif text.startswith("/water"):
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        if m:
            val = float(m.group(1))
            add_l = val / 1000.0 if val > 15 else val
            existing = db.execute("SELECT water_l FROM daily_checkins WHERE date=? AND profile_id=?", (date_str, pid)).fetchone()
            curr_w = float(existing["water_l"]) if existing and existing["water_l"] else 0.0
            new_w = round(curr_w + add_l, 2)
            saved = _upsert_checkin(db, date_str, {"water_l": new_w}, pid)
            return jsonify({"ok": True, "command": "water", "reply": f"💧 Water updated: {new_w:.2f}L / {profile['target_water_l']}L", "checkin": saved})
    elif text.startswith("/sync"):
        sim = generate_simulated_sync_payload(date_str, wk_info["week_num"], wk_info["step_target"])
        saved = _upsert_checkin(db, date_str, sim["merged"], pid)
        return jsonify({"ok": True, "command": "sync", "reply": f"🔄 Synced Garmin + MFP for {date_str}: {saved['steps']:,} steps, {saved['protein_g']}g P, {saved['calories']} kcal", "checkin": saved})
    elif text.startswith("/checkin"):
        sheet = _build_week_sheet(db, profile, wk_info["week_num"])
        summary = format_weekly_telegram_summary(profile, wk_info["week_num"], sheet["rows"], sheet["averages"])
        return jsonify({"ok": True, "command": "checkin", "reply": summary, "averages": sheet["averages"]})

    # Default: /status
    row = db.execute("SELECT * FROM daily_checkins WHERE date=? AND profile_id=?", (date_str, pid)).fetchone()
    checkin = dict(row) if row else _upsert_checkin(db, date_str, {}, pid)
    wtd = _compute_win_the_day_score(checkin, profile, wk_info["step_target"])
    reply = (
        f"📊 CS Fitness Status ({date_str}) — Score: {wtd['score']}/100\n"
        f"👟 Steps: {checkin['steps']:,}/{wk_info['step_target']:,} | "
        f"🥩 Protein: {checkin['protein_g']}g/{profile['target_protein_g']}g | "
        f"🔥 Cals: {checkin['calories']}/{profile['target_calories']} | "
        f"💧 Water: {checkin['water_l']}L/{profile['target_water_l']}L"
    )
    return jsonify({"ok": True, "command": "status", "reply": reply, "checkin": checkin, "win_the_day": wtd})


@challenge_bp.route("/api/challenge/whatsapp/feed", methods=["GET", "POST"])
def api_challenge_whatsapp_feed():
    db = get_db()
    if request.method == "POST":
        data = request.get_json() or {}
        sender = data.get("sender") or "Ewan t"
        msg = data.get("message") or ""
        tags = re.findall(r"#[A-Za-z0-9_]+", msg) or ["#Ewan", "#steps", "#macros", "#winTheDay"]
        steps_val = data.get("steps")
        db.execute(
            "INSERT INTO whatsapp_posts (sender, role, posted_at, message, hashtags_json, steps_extracted, category) VALUES (?,?,?,?,?,?,?)",
            (sender, data.get("role", "member"), datetime.now().strftime("%Y-%m-%d %H:%M"), msg, json.dumps(tags), steps_val, "accountability"),
        )
        db.commit()
    rows = db.execute("SELECT * FROM whatsapp_posts ORDER BY id DESC LIMIT 40").fetchall()
    posts = []
    for r in rows:
        d = dict(r)
        try:
            d["hashtags"] = json.loads(d.get("hashtags_json") or "[]")
        except Exception:
            d["hashtags"] = []
        posts.append(d)
    return jsonify({"posts": posts})


@challenge_bp.route("/api/challenge/whatsapp/import", methods=["POST"])
def api_challenge_whatsapp_import():
    db = get_db()
    if "file" in request.files:
        f = request.files["file"]
        raw = f.read()
        fname = f.filename or "chat.txt"
    else:
        data = request.get_json(silent=True) or {}
        raw = data.get("chat_text") or request.get_data()
        fname = data.get("filename", "chat.txt")

    parsed = parse_whatsapp_export(raw, fname)
    added = 0
    for p in parsed["posts"][:35]:
        db.execute(
            "INSERT INTO whatsapp_posts (sender, role, posted_at, message, hashtags_json, steps_extracted, category) VALUES (?,?,?,?,?,?,?)",
            (p["sender"], p["role"], p["posted_at"], p["message"], json.dumps(p["hashtags"]), p["steps_extracted"], p["category"]),
        )
        added += 1
    db.commit()
    parsed["saved_to_feed"] = added
    return jsonify(parsed)


@challenge_bp.route("/api/challenge/photos", methods=["GET", "POST"])
def api_challenge_photos():
    db = get_db()
    profile = _get_active_profile(db, request.args.get("profile_id", type=int))
    pid = int(profile["id"])
    if request.method == "GET":
        rows = db.execute("SELECT * FROM progress_photos WHERE profile_id=? ORDER BY week_num, id", (pid,)).fetchall()
        return jsonify([dict(r) for r in rows])
    data = request.get_json() or {}
    db.execute(
        """INSERT INTO progress_photos (profile_id, week_num, pose, taken_date, weight_kg, fasted_confirmed, lighting_note, photo_data_url, notes)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            pid,
            int(data.get("week_num", 1)),
            data.get("pose", "Front"),
            (data.get("taken_date") or datetime.now().strftime("%Y-%m-%d"))[:10],
            data.get("weight_kg", profile.get("start_weight_kg", 84.0)),
            1 if data.get("fasted_confirmed", True) else 0,
            data.get("lighting_note", "Morning natural light, tripod at waist height"),
            data.get("photo_data_url", ""),
            data.get("notes", ""),
        ),
    )
    db.commit()
    rows = db.execute("SELECT * FROM progress_photos WHERE profile_id=? ORDER BY week_num, id", (pid,)).fetchall()
    return jsonify([dict(r) for r in rows]), 201


@challenge_bp.route("/api/challenge/rhythm/<int:task_id>/toggle", methods=["POST"])
def api_challenge_rhythm_toggle(task_id):
    db = get_db()
    row = db.execute("SELECT * FROM weekly_rhythm_tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    new_val = 0 if row["completed"] else 1
    db.execute("UPDATE weekly_rhythm_tasks SET completed=? WHERE id=?", (new_val, task_id))
    db.commit()
    return jsonify({"id": task_id, "completed": bool(new_val)})


@challenge_bp.route("/api/challenge/coach/cohort", methods=["GET"])
def api_challenge_coach_cohort():
    db = get_db()
    if not _is_current_user_admin(db):
        return jsonify({"ok": False, "error": "Admin access required"}), 403
    profiles = [dict(r) for r in db.execute("SELECT * FROM challenge_profiles ORDER BY id").fetchall()]
    wa_posts = [dict(r) for r in db.execute("SELECT * FROM whatsapp_posts WHERE role='member' ORDER BY id DESC LIMIT 20").fetchall()]
    for p in profiles:
        try:
            p["weekly_targets"] = json.loads(p.get("weekly_targets_json") or "[]")
        except Exception:
            p["weekly_targets"] = []
    return jsonify({
        "cohort_name": "CS Fitness 8-Week Transformation — 19 Oct 2026 Cohort",
        "challenger_count": len(profiles),
        "challengers": profiles,
        "recent_accountability_posts": wa_posts,
    })



