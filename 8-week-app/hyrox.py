import csv
import io
import random
import re
import time
from datetime import datetime, date
from flask import Blueprint, jsonify, render_template, request, Response, abort
from database import get_db

hyrox_bp = Blueprint("hyrox", __name__)

# ── 16-Split Sequence (No Roxzone — Extended Run Loop) ──────────────────────

HYROX_SPLITS_TEMPLATE = [
    {"split_index": 1,  "split_type": "run",     "station_key": "run_1",          "label": "Run 1",                        "short_label": "R1"},
    {"split_index": 2,  "split_type": "station", "station_key": "skierg",         "label": "1. SkiErg (1,000m)",           "short_label": "S1 SkiErg"},
    {"split_index": 3,  "split_type": "run",     "station_key": "run_2",          "label": "Run 2",                        "short_label": "R2"},
    {"split_index": 4,  "split_type": "station", "station_key": "sled_push",      "label": "2. Sled Push (50m)",           "short_label": "S2 Push"},
    {"split_index": 5,  "split_type": "run",     "station_key": "run_3",          "label": "Run 3",                        "short_label": "R3"},
    {"split_index": 6,  "split_type": "station", "station_key": "sled_pull",      "label": "3. Sled Pull (50m)",           "short_label": "S3 Pull"},
    {"split_index": 7,  "split_type": "run",     "station_key": "run_4",          "label": "Run 4",                        "short_label": "R4"},
    {"split_index": 8,  "split_type": "station", "station_key": "bbj",            "label": "4. Burpee Broad Jumps (80m)",  "short_label": "S4 BBJ"},
    {"split_index": 9,  "split_type": "run",     "station_key": "run_5",          "label": "Run 5",                        "short_label": "R5"},
    {"split_index": 10, "split_type": "station", "station_key": "row",            "label": "5. Row (1,000m)",              "short_label": "S5 Row"},
    {"split_index": 11, "split_type": "run",     "station_key": "run_6",          "label": "Run 6",                        "short_label": "R6"},
    {"split_index": 12, "split_type": "station", "station_key": "farmers_carry",  "label": "6. Farmers Carry (200m)",      "short_label": "S6 Carry"},
    {"split_index": 13, "split_type": "run",     "station_key": "run_7",          "label": "Run 7",                        "short_label": "R7"},
    {"split_index": 14, "split_type": "station", "station_key": "sandbag_lunges", "label": "7. Sandbag Lunges (100m)",     "short_label": "S7 Lunges"},
    {"split_index": 15, "split_type": "run",     "station_key": "run_8",          "label": "Run 8",                        "short_label": "R8"},
    {"split_index": 16, "split_type": "station", "station_key": "wall_balls",     "label": "8. Wall Balls",                "short_label": "S8 Wall Balls"},
]

AGE_CATEGORIES = [
    "U24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59", "60+"
]

# ── Built-in Official HYROX Weights & Reps Matrix per Division ──────────────

HYROX_DIVISIONS = {
    "women_open": {
        "key": "women_open",
        "label": "Women Open",
        "short_label": "W Open",
        "color": "#38bdf8",
        "is_doubles": False,
        "wall_ball_target_reps": 75,
        "stations": {
            "skierg":         {"distance": "1,000m", "weight": "Damper open", "prescription": "SkiErg 1000m"},
            "sled_push":      {"distance": "50m",    "weight": "102 kg (incl. sled)", "prescription": "Sled Push 50m @ 102 kg"},
            "sled_pull":      {"distance": "50m",    "weight": "78 kg (incl. sled)",  "prescription": "Sled Pull 50m @ 78 kg"},
            "bbj":            {"distance": "80m",    "weight": "Bodyweight",          "prescription": "Burpee Broad Jump 80m"},
            "row":            {"distance": "1,000m", "weight": "Damper open",         "prescription": "Row 1000m"},
            "farmers_carry":  {"distance": "200m",   "weight": "2×16 kg",             "prescription": "Farmers Carry 200m @ 2×16 kg"},
            "sandbag_lunges": {"distance": "100m",   "weight": "10 kg",               "prescription": "Sandbag Lunges 100m @ 10 kg"},
            "wall_balls":     {"distance": "75 reps","weight": "4 kg (2.7m target)",  "prescription": "Wall Balls 75 reps @ 4 kg (2.7m target)"},
        },
    },
    "women_pro": {
        "key": "women_pro",
        "label": "Women Pro",
        "short_label": "W Pro",
        "color": "#f43f5e",
        "is_doubles": False,
        "wall_ball_target_reps": 100,
        "stations": {
            "skierg":         {"distance": "1,000m",  "weight": "Damper open", "prescription": "SkiErg 1000m"},
            "sled_push":      {"distance": "50m",     "weight": "152 kg (incl. sled)", "prescription": "Sled Push 50m @ 152 kg"},
            "sled_pull":      {"distance": "50m",     "weight": "103 kg (incl. sled)", "prescription": "Sled Pull 50m @ 103 kg"},
            "bbj":            {"distance": "80m",     "weight": "Bodyweight",          "prescription": "Burpee Broad Jump 80m"},
            "row":            {"distance": "1,000m",  "weight": "Damper open",         "prescription": "Row 1000m"},
            "farmers_carry":  {"distance": "200m",    "weight": "2×24 kg",             "prescription": "Farmers Carry 200m @ 2×24 kg"},
            "sandbag_lunges": {"distance": "100m",    "weight": "20 kg",               "prescription": "Sandbag Lunges 100m @ 20 kg"},
            "wall_balls":     {"distance": "100 reps","weight": "6 kg (2.7m target)",  "prescription": "Wall Balls 100 reps @ 6 kg (2.7m target)"},
        },
    },
    "men_open": {
        "key": "men_open",
        "label": "Men Open",
        "short_label": "M Open",
        "color": "#3DFF4F",
        "is_doubles": False,
        "wall_ball_target_reps": 100,
        "stations": {
            "skierg":         {"distance": "1,000m",  "weight": "Damper open", "prescription": "SkiErg 1000m"},
            "sled_push":      {"distance": "50m",     "weight": "152 kg (incl. sled)", "prescription": "Sled Push 50m @ 152 kg"},
            "sled_pull":      {"distance": "50m",     "weight": "103 kg (incl. sled)", "prescription": "Sled Pull 50m @ 103 kg"},
            "bbj":            {"distance": "80m",     "weight": "Bodyweight",          "prescription": "Burpee Broad Jump 80m"},
            "row":            {"distance": "1,000m",  "weight": "Damper open",         "prescription": "Row 1000m"},
            "farmers_carry":  {"distance": "200m",    "weight": "2×24 kg",             "prescription": "Farmers Carry 200m @ 2×24 kg"},
            "sandbag_lunges": {"distance": "100m",    "weight": "20 kg",               "prescription": "Sandbag Lunges 100m @ 20 kg"},
            "wall_balls":     {"distance": "100 reps","weight": "6 kg (3.0m target)",  "prescription": "Wall Balls 100 reps @ 6 kg (3.0m target)"},
        },
    },
    "men_pro": {
        "key": "men_pro",
        "label": "Men Pro",
        "short_label": "M Pro",
        "color": "#f59e0b",
        "is_doubles": False,
        "wall_ball_target_reps": 100,
        "stations": {
            "skierg":         {"distance": "1,000m",  "weight": "Damper open", "prescription": "SkiErg 1000m"},
            "sled_push":      {"distance": "50m",     "weight": "202 kg (incl. sled)", "prescription": "Sled Push 50m @ 202 kg"},
            "sled_pull":      {"distance": "50m",     "weight": "153 kg (incl. sled)", "prescription": "Sled Pull 50m @ 153 kg"},
            "bbj":            {"distance": "80m",     "weight": "Bodyweight",          "prescription": "Burpee Broad Jump 80m"},
            "row":            {"distance": "1,000m",  "weight": "Damper open",         "prescription": "Row 1000m"},
            "farmers_carry":  {"distance": "200m",    "weight": "2×32 kg",             "prescription": "Farmers Carry 200m @ 2×32 kg"},
            "sandbag_lunges": {"distance": "100m",    "weight": "30 kg",               "prescription": "Sandbag Lunges 100m @ 30 kg"},
            "wall_balls":     {"distance": "100 reps","weight": "9 kg (3.0m target)",  "prescription": "Wall Balls 100 reps @ 9 kg (3.0m target)"},
        },
    },
    "mixed_doubles": {
        "key": "mixed_doubles",
        "label": "Mixed Doubles",
        "short_label": "Mixed Dbl",
        "color": "#a855f7",
        "is_doubles": True,
        "wall_ball_target_reps": 100,
        "stations": {
            "skierg":         {"distance": "1,000m (split)",  "weight": "Partners split work", "prescription": "SkiErg 1000m (split)"},
            "sled_push":      {"distance": "50m (split)",     "weight": "152 kg (incl. sled)", "prescription": "Sled Push 50m @ 152 kg"},
            "sled_pull":      {"distance": "50m (split)",     "weight": "103 kg (incl. sled)", "prescription": "Sled Pull 50m @ 103 kg"},
            "bbj":            {"distance": "80m (split)",     "weight": "Bodyweight (split)",  "prescription": "Burpee Broad Jump 80m (split)"},
            "row":            {"distance": "1,000m (split)",  "weight": "Partners split work", "prescription": "Row 1000m (split)"},
            "farmers_carry":  {"distance": "200m (split)",    "weight": "2×24 kg",             "prescription": "Farmers Carry 200m @ 2×24 kg"},
            "sandbag_lunges": {"distance": "100m (split)",    "weight": "20 kg",               "prescription": "Sandbag Lunges 100m @ 20 kg"},
            "wall_balls":     {"distance": "100 reps (split)","weight": "6 kg (2.7m W / 3.0m M)", "prescription": "Wall Balls 100 reps @ 6 kg (2.7m W / 3.0m M)"},
        },
    },
    "women_doubles": {
        "key": "women_doubles",
        "label": "Women Doubles",
        "short_label": "W Doubles",
        "color": "#ec4899",
        "is_doubles": True,
        "wall_ball_target_reps": 100,
        "stations": {
            "skierg":         {"distance": "1,000m (split)",  "weight": "Partners split work", "prescription": "SkiErg 1000m (split)"},
            "sled_push":      {"distance": "50m (split)",     "weight": "102 kg (incl. sled)", "prescription": "Sled Push 50m @ 102 kg"},
            "sled_pull":      {"distance": "50m (split)",     "weight": "78 kg (incl. sled)",  "prescription": "Sled Pull 50m @ 78 kg"},
            "bbj":            {"distance": "80m (split)",     "weight": "Bodyweight (split)",  "prescription": "Burpee Broad Jump 80m (split)"},
            "row":            {"distance": "1,000m (split)",  "weight": "Partners split work", "prescription": "Row 1000m (split)"},
            "farmers_carry":  {"distance": "200m (split)",    "weight": "2×16 kg",             "prescription": "Farmers Carry 200m @ 2×16 kg"},
            "sandbag_lunges": {"distance": "100m (split)",    "weight": "10 kg",               "prescription": "Sandbag Lunges 100m @ 10 kg"},
            "wall_balls":     {"distance": "100 reps (split)","weight": "4 kg (2.7m target)",  "prescription": "Wall Balls 100 reps @ 4 kg (2.7m target)"},
        },
    },
    "men_doubles": {
        "key": "men_doubles",
        "label": "Men Doubles",
        "short_label": "M Doubles",
        "color": "#14b8a6",
        "is_doubles": True,
        "wall_ball_target_reps": 100,
        "stations": {
            "skierg":         {"distance": "1,000m (split)",  "weight": "Partners split work", "prescription": "SkiErg 1000m (split)"},
            "sled_push":      {"distance": "50m (split)",     "weight": "152 kg (incl. sled)", "prescription": "Sled Push 50m @ 152 kg"},
            "sled_pull":      {"distance": "50m (split)",     "weight": "103 kg (incl. sled)", "prescription": "Sled Pull 50m @ 103 kg"},
            "bbj":            {"distance": "80m (split)",     "weight": "Bodyweight (split)",  "prescription": "Burpee Broad Jump 80m (split)"},
            "row":            {"distance": "1,000m (split)",  "weight": "Partners split work", "prescription": "Row 1000m (split)"},
            "farmers_carry":  {"distance": "200m (split)",    "weight": "2×24 kg",             "prescription": "Farmers Carry 200m @ 2×24 kg"},
            "sandbag_lunges": {"distance": "100m (split)",    "weight": "20 kg",               "prescription": "Sandbag Lunges 100m @ 20 kg"},
            "wall_balls":     {"distance": "100 reps (split)","weight": "6 kg (3.0m target)",  "prescription": "Wall Balls 100 reps @ 6 kg (3.0m target)"},
        },
    },
}


# ── Formatting & Parsing Helpers ────────────────────────────────────────────

def format_ms(ms, include_hours=False):
    if ms is None:
        return "—"
    try:
        ms = int(ms)
    except (TypeError, ValueError):
        return "—"
    neg = ms < 0
    total_sec = abs(ms) // 1000
    hours = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    prefix = "-" if neg else ""
    if hours > 0 or include_hours:
        return f"{prefix}{hours}:{mins:02d}:{secs:02d}"
    return f"{prefix}{mins:02d}:{secs:02d}"


def format_delta_ms(delta_ms):
    if delta_ms is None:
        return "—"
    try:
        delta_ms = int(delta_ms)
    except (TypeError, ValueError):
        return "—"
    if delta_ms == 0:
        return "0:00"
    sign = "-" if delta_ms < 0 else "+"
    total_sec = abs(delta_ms) // 1000
    mins = total_sec // 60
    secs = total_sec % 60
    return f"{sign}{mins}:{secs:02d}"


def parse_duration_to_ms(val):
    """Parse MM:SS, H:MM:SS, or numeric milliseconds/seconds into integer ms."""
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip()
    if not s:
        return None
    if ":" in s:
        parts = [p.strip() for p in s.split(":")]
        try:
            if len(parts) == 2:
                m = int(parts[0])
                sec = float(parts[1])
                return int(round((m * 60 + sec) * 1000))
            elif len(parts) == 3:
                h = int(parts[0])
                m = int(parts[1])
                sec = float(parts[2])
                return int(round((h * 3600 + m * 60 + sec) * 1000))
        except ValueError:
            return None
    try:
        num = float(s)
        if num >= 1000:
            return int(num)
        return int(round(num * 1000))
    except ValueError:
        return None


def normalize_division(raw):
    if not raw:
        return "men_open"
    s = re.sub(r"[^a-z0-9]+", "_", str(raw).strip().lower()).strip("_")
    if s in HYROX_DIVISIONS:
        return s
    if "mixed" in s or ("mix" in s and "double" in s):
        return "mixed_doubles"
    if ("women" in s or "female" in s or "ladies" in s or s.startswith("w_")) and ("double" in s or "pair" in s):
        return "women_doubles"
    if ("men" in s or "male" in s or s.startswith("m_")) and ("double" in s or "pair" in s):
        return "men_doubles"
    if ("women" in s or "female" in s or "ladies" in s or s.startswith("w_")) and "pro" in s:
        return "women_pro"
    if ("women" in s or "female" in s or "ladies" in s or s.startswith("w_")):
        return "women_open"
    if ("men" in s or "male" in s or s.startswith("m_")) and "pro" in s:
        return "men_pro"
    if "double" in s or "pair" in s:
        return "mixed_doubles"
    return "men_open"


def normalize_age_category(raw_age_or_dob):
    if not raw_age_or_dob:
        return "30-34"
    s = str(raw_age_or_dob).strip()
    if s in AGE_CATEGORIES:
        return s
    s_up = s.upper()
    if s_up in ("U24", "UNDER 24", "<24", "16-24", "18-24"):
        return "U24"
    if s_up in ("60+", "60-64", "65-69", "70+"):
        return "60+"
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            dob_dt = datetime.strptime(s[:10], fmt).date()
            today = date(2026, 11, 14)
            age = today.year - dob_dt.year - ((today.month, today.day) < (dob_dt.month, dob_dt.day))
            return _age_int_to_category(age)
        except ValueError:
            pass
    m = re.search(r"\b(\d{2})\b", s)
    if m:
        age = int(m.group(1))
        for cat in AGE_CATEGORIES:
            if "-" in cat:
                lo, hi = map(int, cat.split("-"))
                if lo <= age <= hi:
                    return cat
        return _age_int_to_category(age)
    return "30-34"


def _age_int_to_category(age):
    if age < 25:
        return "U24"
    elif age < 30:
        return "25-29"
    elif age < 35:
        return "30-34"
    elif age < 40:
        return "35-39"
    elif age < 45:
        return "40-44"
    elif age < 50:
        return "45-49"
    elif age < 55:
        return "50-54"
    elif age < 60:
        return "55-59"
    return "60+"


def get_prescription_for_split(division_key, split_index):
    div = HYROX_DIVISIONS.get(division_key) or HYROX_DIVISIONS["men_open"]
    tmpl = HYROX_SPLITS_TEMPLATE[split_index - 1]
    if tmpl["split_type"] == "run":
        return {
            "split_index": split_index,
            "split_type": "run",
            "station_key": tmpl["station_key"],
            "label": tmpl["label"],
            "distance": "Extended Run Loop (No Roxzone)",
            "weight": "Pace / Run",
            "prescription": f"{tmpl['label']} — Standard Gym Run Loop",
        }
    st_key = tmpl["station_key"]
    st_info = div["stations"].get(st_key, {})
    return {
        "split_index": split_index,
        "split_type": "station",
        "station_key": st_key,
        "label": tmpl["label"],
        "distance": st_info.get("distance", ""),
        "weight": st_info.get("weight", ""),
        "prescription": st_info.get("prescription", tmpl["label"]),
    }


# ── Database Schema & Initialization ────────────────────────────────────────

def ensure_hyrox_tables(db):
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS hyrox_events (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            name                TEXT NOT NULL,
            event_date          TEXT NOT NULL,
            venue               TEXT NOT NULL DEFAULT 'CS Performance Studio',
            wave_interval_mins  INTEGER NOT NULL DEFAULT 15,
            lanes_per_wave      INTEGER NOT NULL DEFAULT 4,
            status              TEXT NOT NULL DEFAULT 'live',
            notes               TEXT NOT NULL DEFAULT '',
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS hyrox_athletes (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name           TEXT NOT NULL,
            email               TEXT NOT NULL DEFAULT '',
            dob                 TEXT NOT NULL DEFAULT '',
            age_category        TEXT NOT NULL DEFAULT '30-34',
            gender              TEXT NOT NULL DEFAULT '',
            teamup_customer_id  TEXT NOT NULL DEFAULT '',
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS hyrox_heats (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id            INTEGER NOT NULL REFERENCES hyrox_events(id) ON DELETE CASCADE,
            heat_number         INTEGER NOT NULL DEFAULT 1,
            name                TEXT NOT NULL,
            start_time          TEXT NOT NULL DEFAULT '08:00',
            max_lanes           INTEGER NOT NULL DEFAULT 4,
            status              TEXT NOT NULL DEFAULT 'scheduled'
        );

        CREATE TABLE IF NOT EXISTS hyrox_entries (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id            INTEGER NOT NULL REFERENCES hyrox_events(id) ON DELETE CASCADE,
            heat_id             INTEGER REFERENCES hyrox_heats(id) ON DELETE SET NULL,
            athlete_id          INTEGER REFERENCES hyrox_athletes(id) ON DELETE SET NULL,
            partner_athlete_id  INTEGER REFERENCES hyrox_athletes(id) ON DELETE SET NULL,
            display_name        TEXT NOT NULL,
            partner_name        TEXT NOT NULL DEFAULT '',
            email               TEXT NOT NULL DEFAULT '',
            bib_number          TEXT NOT NULL DEFAULT '',
            division            TEXT NOT NULL DEFAULT 'men_open',
            age_category        TEXT NOT NULL DEFAULT '30-34',
            volunteer_name      TEXT NOT NULL DEFAULT '',
            judge_pin           TEXT NOT NULL DEFAULT '',
            status              TEXT NOT NULL DEFAULT 'scheduled',
            started_at_ms       INTEGER,
            finished_at_ms      INTEGER,
            total_ms            INTEGER,
            run_total_ms        INTEGER,
            station_total_ms    INTEGER,
            penalty_ms          INTEGER NOT NULL DEFAULT 0,
            wall_ball_reps      INTEGER NOT NULL DEFAULT 0,
            notes               TEXT NOT NULL DEFAULT '',
            updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS hyrox_splits (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id            INTEGER NOT NULL REFERENCES hyrox_entries(id) ON DELETE CASCADE,
            split_index         INTEGER NOT NULL,
            split_type          TEXT NOT NULL,
            station_key         TEXT NOT NULL,
            label               TEXT NOT NULL,
            duration_ms         INTEGER,
            completed_at_ms     INTEGER,
            edited_by           TEXT NOT NULL DEFAULT '',
            notes               TEXT NOT NULL DEFAULT '',
            UNIQUE(entry_id, split_index)
        );
        """
    )
    count = db.execute("SELECT COUNT(*) as c FROM hyrox_events").fetchone()["c"]
    if count == 0:
        seed_default_hyrox_data(db)
        db.commit()


def find_or_create_athlete(db, full_name, email="", dob="", age_category="30-34", gender="", teamup_customer_id=""):
    full_name = (full_name or "").strip()
    email = (email or "").strip().lower()
    if not full_name:
        return None
    row = None
    if email:
        row = db.execute(
            "SELECT * FROM hyrox_athletes WHERE LOWER(email)=? LIMIT 1",
            (email,)
        ).fetchone()
    if not row:
        row = db.execute(
            "SELECT * FROM hyrox_athletes WHERE LOWER(full_name)=? LIMIT 1",
            (full_name.lower(),)
        ).fetchone()
    if row:
        new_email = email or row["email"]
        new_dob = dob or row["dob"]
        new_age = age_category or row["age_category"]
        new_gender = gender or row["gender"]
        new_tcid = teamup_customer_id or row["teamup_customer_id"]
        db.execute(
            "UPDATE hyrox_athletes SET email=?, dob=?, age_category=?, gender=?, teamup_customer_id=? WHERE id=?",
            (new_email, new_dob, new_age, new_gender, new_tcid, row["id"])
        )
        return row["id"]
    cur = db.execute(
        "INSERT INTO hyrox_athletes (full_name, email, dob, age_category, gender, teamup_customer_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (full_name, email, dob, age_category or "30-34", gender, teamup_customer_id)
    )
    return cur.lastrowid


def ensure_entry_splits(db, entry_id):
    existing = {
        r["split_index"]
        for r in db.execute("SELECT split_index FROM hyrox_splits WHERE entry_id=?", (entry_id,)).fetchall()
    }
    for tmpl in HYROX_SPLITS_TEMPLATE:
        if tmpl["split_index"] not in existing:
            db.execute(
                "INSERT INTO hyrox_splits (entry_id, split_index, split_type, station_key, label) "
                "VALUES (?, ?, ?, ?, ?)",
                (entry_id, tmpl["split_index"], tmpl["split_type"], tmpl["station_key"], tmpl["label"])
            )


def recalculate_entry_totals(db, entry_id):
    entry = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
    if not entry:
        return None
    ensure_entry_splits(db, entry_id)
    splits = db.execute(
        "SELECT * FROM hyrox_splits WHERE entry_id=? ORDER BY split_index ASC",
        (entry_id,)
    ).fetchall()

    run_ms = 0
    station_ms = 0
    completed_count = 0
    for s in splits:
        if s["duration_ms"] is not None:
            completed_count += 1
            if s["split_type"] == "run":
                run_ms += int(s["duration_ms"])
            else:
                station_ms += int(s["duration_ms"])

    penalty_ms = int(entry["penalty_ms"] or 0)
    total_ms = (run_ms + station_ms + penalty_ms) if completed_count > 0 else None

    status = entry["status"]
    finished_at_ms = entry["finished_at_ms"]
    if completed_count == 16:
        status = "finished"
        if not finished_at_ms and entry["started_at_ms"] and total_ms:
            finished_at_ms = int(entry["started_at_ms"]) + total_ms
    elif completed_count > 0 and status == "scheduled":
        status = "racing"

    db.execute(
        "UPDATE hyrox_entries SET run_total_ms=?, station_total_ms=?, total_ms=?, status=?, finished_at_ms=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (
            run_ms if completed_count > 0 else None,
            station_ms if completed_count > 0 else None,
            total_ms,
            status,
            finished_at_ms,
            entry_id,
        ),
    )
    return {
        "run_total_ms": run_ms if completed_count > 0 else None,
        "station_total_ms": station_ms if completed_count > 0 else None,
        "total_ms": total_ms,
        "completed_splits": completed_count,
        "status": status,
    }


def _generate_unique_pin(db, event_id, preferred_pin=None):
    used = {
        r["judge_pin"]
        for r in db.execute("SELECT judge_pin FROM hyrox_entries WHERE event_id=?", (event_id,)).fetchall()
        if r["judge_pin"]
    }
    if preferred_pin and preferred_pin not in used:
        return preferred_pin
    for candidate in range(1001, 9999):
        pin = str(candidate)
        if pin not in used:
            return pin
    return str(random.randint(1000, 9999))


# ── Pre-seed Realistic Demo Event & Baseline Sim ────────────────────────────

def seed_default_hyrox_data(db):
    now_ms = int(time.time() * 1000)

    # 1. Baseline Event (September 2026) for Sim-over-Sim "Roxfit-Lite" Progression
    cur_base = db.execute(
        "INSERT INTO hyrox_events (name, event_date, venue, wave_interval_mins, lanes_per_wave, status, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "CS Performance HYROX Baseline Sim — Sep 2026",
            "2026-09-19",
            "CS Performance Studio",
            15,
            4,
            "completed",
            "Autumn Baseline HYROX Simulation (Extended Run Loop, No Roxzone)",
        ),
    )
    base_event_id = cur_base.lastrowid
    cur_base_heat = db.execute(
        "INSERT INTO hyrox_heats (event_id, heat_number, name, start_time, max_lanes, status) "
        "VALUES (?, 1, 'Wave 1 — 08:00', '08:00', 4, 'completed')",
        (base_event_id,),
    )
    base_heat_id = cur_base_heat.lastrowid

    # Persistent Athletes
    ewan_id = find_or_create_athlete(db, "Ewan Taylor", "taylor.ewan@googlemail.com", "1989-04-12", "35-39", "M", "TU-1001")
    alan_id = find_or_create_athlete(db, "Alan Mackay", "alan.mackay@example.com", "1984-08-22", "40-44", "M", "TU-1002")
    sarah_id = find_or_create_athlete(db, "Sarah Jenkins", "sarah.jenkins@example.com", "1993-02-15", "30-34", "F", "TU-1003")
    laura_id = find_or_create_athlete(db, "Laura Mitchell", "laura.mitchell@example.com", "1992-11-03", "30-34", "F", "TU-1004")
    chris_id = find_or_create_athlete(db, "Chris Smith", "chris.smith@example.com", "1988-06-19", "35-39", "M", "TU-1005")
    emma_id = find_or_create_athlete(db, "Emma Wallace", "emma.wallace@example.com", "1990-09-25", "35-39", "F", "TU-1006")
    callum_id = find_or_create_athlete(db, "Callum Fraser", "callum.fraser@example.com", "1998-01-10", "25-29", "M", "TU-1007")
    kirsty_id = find_or_create_athlete(db, "Kirsty Grant", "kirsty.grant@example.com", "1994-05-14", "30-34", "F", "TU-1008")
    megan_id = find_or_create_athlete(db, "Megan Scott", "megan.scott@example.com", "1995-07-30", "30-34", "F", "TU-1009")
    ross_id = find_or_create_athlete(db, "Ross MacLeod", "ross.macleod@example.com", "1993-12-01", "30-34", "M", "TU-1010")
    hannah_id = find_or_create_athlete(db, "Hannah Reid", "hannah.reid@example.com", "1999-03-18", "25-29", "F", "TU-1011")
    dave_id = find_or_create_athlete(db, "Dave Kerr", "dave.kerr@example.com", "1987-10-08", "35-39", "M", "TU-1012")
    mark_id = find_or_create_athlete(db, "Mark Stewart", "mark.stewart@example.com", "1988-02-27", "35-39", "M", "TU-1013")

    def _seed_finished_entry(event_id, heat_id, athlete_id, partner_athlete_id, display_name, partner_name,
                             email, bib, division, age_cat, volunteer, pin, split_secs, wall_balls=100, start_offset_ms=7200000):
        start_ms = now_ms - start_offset_ms
        cur = db.execute(
            "INSERT INTO hyrox_entries (event_id, heat_id, athlete_id, partner_athlete_id, display_name, partner_name, "
            "email, bib_number, division, age_category, volunteer_name, judge_pin, status, started_at_ms, wall_ball_reps) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'finished', ?, ?)",
            (event_id, heat_id, athlete_id, partner_athlete_id, display_name, partner_name,
             email, bib, division, age_cat, volunteer, pin, start_ms, wall_balls)
        )
        eid = cur.lastrowid
        ensure_entry_splits(db, eid)
        elapsed = 0
        for idx, secs in enumerate(split_secs, start=1):
            dur_ms = int(secs * 1000)
            elapsed += dur_ms
            db.execute(
                "UPDATE hyrox_splits SET duration_ms=?, completed_at_ms=? WHERE entry_id=? AND split_index=?",
                (dur_ms, start_ms + elapsed, eid, idx)
            )
        recalculate_entry_totals(db, eid)
        return eid

    # Ewan's Sep 2026 Baseline Sim: Total 1:14:15 (4455s)
    ewan_sep_splits = [
        282, 260,
        295, 215,
        305, 255,
        312, 290,
        310, 268,
        302, 165,
        318, 258,
        305, 315,
    ]
    _seed_finished_entry(
        base_event_id, base_heat_id, ewan_id, None, "Ewan Taylor", "",
        "taylor.ewan@googlemail.com", "101", "men_open", "35-39", "Coach Chris", "9101",
        ewan_sep_splits, wall_balls=100, start_offset_ms=86400000 * 55
    )

    # Sarah's Sep 2026 Baseline Sim: Total 1:18:10
    sarah_sep_splits = [
        298, 275,
        308, 222,
        315, 265,
        322, 305,
        320, 282,
        314, 178,
        328, 270,
        318, 370,
    ]
    _seed_finished_entry(
        base_event_id, base_heat_id, sarah_id, None, "Sarah Jenkins", "",
        "sarah.jenkins@example.com", "103", "women_open", "30-34", "Coach Laura", "9103",
        sarah_sep_splits, wall_balls=75, start_offset_ms=86400000 * 55
    )

    # 2. Featured Event: "CS Performance HYROX Sim — Nov 2026"
    cur_nov = db.execute(
        "INSERT INTO hyrox_events (name, event_date, venue, wave_interval_mins, lanes_per_wave, status, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "CS Performance HYROX Sim — Nov 2026",
            "2026-11-14",
            "CS Performance Studio",
            15,
            4,
            "live",
            "Full 16-Split Gym Simulation (Extended Run Loop — No Roxzone). 1 Volunteer Judge per Athlete/Pair.",
        ),
    )
    nov_event_id = cur_nov.lastrowid

    heats_spec = [
        (1, "Wave 1 — 08:00", "08:00", 4, "completed"),
        (2, "Wave 2 — 08:15", "08:15", 4, "racing"),
        (3, "Wave 3 — 08:30", "08:30", 4, "scheduled"),
        (4, "Wave 4 — 08:45", "08:45", 4, "scheduled"),
    ]
    heat_ids = {}
    for h_num, h_name, h_time, h_lanes, h_status in heats_spec:
        c = db.execute(
            "INSERT INTO hyrox_heats (event_id, heat_number, name, start_time, max_lanes, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (nov_event_id, h_num, h_name, h_time, h_lanes, h_status),
        )
        heat_ids[h_num] = c.lastrowid

    # Wave 1 Finished Entries:
    # Ewan Taylor (Men Open) — Improved to 1:09:42 (4182s — 4m33s PB over Sep!)
    ewan_nov_splits = [
        268, 248,
        278, 198,
        286, 238,
        292, 268,
        290, 254,
        284, 152,
        296, 240,
        285, 285,
    ]
    _seed_finished_entry(
        nov_event_id, heat_ids[1], ewan_id, None, "Ewan Taylor", "",
        "taylor.ewan@googlemail.com", "101", "men_open", "35-39", "Coach Chris", "1101",
        ewan_nov_splits, wall_balls=100, start_offset_ms=5400000
    )

    # Alan Mackay (Men Open) — 1:12:08
    alan_nov_splits = [
        275, 255,
        285, 208,
        294, 246,
        302, 280,
        300, 262,
        295, 160,
        306, 252,
        298, 310,
    ]
    _seed_finished_entry(
        nov_event_id, heat_ids[1], alan_id, None, "Alan Mackay", "",
        "alan.mackay@example.com", "102", "men_open", "40-44", "Coach Laura", "1102",
        alan_nov_splits, wall_balls=100, start_offset_ms=5400000
    )

    # Sarah Jenkins (Women Open) — 1:14:36
    sarah_nov_splits = [
        285, 264,
        294, 210,
        302, 252,
        308, 288,
        306, 270,
        300, 168,
        312, 256,
        305, 256,
    ]
    _seed_finished_entry(
        nov_event_id, heat_ids[1], sarah_id, None, "Sarah Jenkins", "",
        "sarah.jenkins@example.com", "103", "women_open", "30-34", "Sam Walker", "1103",
        sarah_nov_splits, wall_balls=75, start_offset_ms=5400000
    )

    # Laura Mitchell (Women Pro) — 1:08:25
    laura_nov_splits = [
        262, 245,
        270, 195,
        278, 232,
        284, 260,
        282, 250,
        276, 150,
        286, 235,
        275, 325,
    ]
    _seed_finished_entry(
        nov_event_id, heat_ids[1], laura_id, None, "Laura Mitchell", "",
        "laura.mitchell@example.com", "104", "women_pro", "30-34", "Jamie Ross", "1104",
        laura_nov_splits, wall_balls=100, start_offset_ms=5400000
    )

    # Chris Smith & Emma Wallace (Mixed Doubles) — 1:03:50
    mixed_nov_splits = [
        252, 220,
        258, 175,
        264, 205,
        268, 230,
        266, 224,
        262, 138,
        270, 208,
        260, 250,
    ]
    _seed_finished_entry(
        nov_event_id, heat_ids[2], chris_id, emma_id, "Chris Smith", "Emma Wallace",
        "chris.smith@example.com", "201", "mixed_doubles", "35-39", "Katie Bell", "1201",
        mixed_nov_splits, wall_balls=100, start_offset_ms=4200000
    )

    # Wave 2 Racing Entries (Live on the gym floor right now!):
    callum_partial = [255, 232, 264, 192, 270, 228, 276, 248, 274, 240, 268]
    callum_elapsed_ms = sum(s * 1000 for s in callum_partial)
    callum_start_ms = now_ms - callum_elapsed_ms - 65000
    cur_cal = db.execute(
        "INSERT INTO hyrox_entries (event_id, heat_id, athlete_id, display_name, email, bib_number, "
        "division, age_category, volunteer_name, judge_pin, status, started_at_ms, wall_ball_reps) "
        "VALUES (?, ?, ?, 'Callum Fraser', 'callum.fraser@example.com', '105', 'men_pro', '25-29', 'Alex Reid', '1105', 'racing', ?, 0)",
        (nov_event_id, heat_ids[2], callum_id, callum_start_ms)
    )
    cal_eid = cur_cal.lastrowid
    ensure_entry_splits(db, cal_eid)
    running_t = 0
    for idx, secs in enumerate(callum_partial, start=1):
        d_ms = secs * 1000
        running_t += d_ms
        db.execute(
            "UPDATE hyrox_splits SET duration_ms=?, completed_at_ms=? WHERE entry_id=? AND split_index=?",
            (d_ms, callum_start_ms + running_t, cal_eid, idx)
        )
    recalculate_entry_totals(db, cal_eid)

    km_partial = [278, 245, 286, 188, 292, 220, 296]
    km_elapsed_ms = sum(s * 1000 for s in km_partial)
    km_start_ms = now_ms - km_elapsed_ms - 95000
    cur_km = db.execute(
        "INSERT INTO hyrox_entries (event_id, heat_id, athlete_id, partner_athlete_id, display_name, partner_name, "
        "email, bib_number, division, age_category, volunteer_name, judge_pin, status, started_at_ms, wall_ball_reps) "
        "VALUES (?, ?, ?, ?, 'Kirsty Grant', 'Megan Scott', 'kirsty.grant@example.com', '202', 'women_doubles', '30-34', 'Sam Walker', '1202', 'racing', ?, 0)",
        (nov_event_id, heat_ids[2], kirsty_id, megan_id, km_start_ms)
    )
    km_eid = cur_km.lastrowid
    ensure_entry_splits(db, km_eid)
    running_t = 0
    for idx, secs in enumerate(km_partial, start=1):
        d_ms = secs * 1000
        running_t += d_ms
        db.execute(
            "UPDATE hyrox_splits SET duration_ms=?, completed_at_ms=? WHERE entry_id=? AND split_index=?",
            (d_ms, km_start_ms + running_t, km_eid, idx)
        )
    recalculate_entry_totals(db, km_eid)

    # Wave 3 & 4 Scheduled Entries (On Deck):
    scheduled_specs = [
        (heat_ids[3], ross_id, None, "Ross MacLeod", "", "ross.macleod@example.com", "106", "men_open", "30-34", "Coach Chris", "1106"),
        (heat_ids[3], hannah_id, None, "Hannah Reid", "", "hannah.reid@example.com", "107", "women_open", "25-29", "Coach Laura", "1107"),
        (heat_ids[4], dave_id, mark_id, "Dave Kerr", "Mark Stewart", "dave.kerr@example.com", "203", "men_doubles", "35-39", "Coach Chris", "1203"),
    ]
    for h_id, a_id, p_id, d_name, p_name, em, bib, div, age_c, vol, pin in scheduled_specs:
        c = db.execute(
            "INSERT INTO hyrox_entries (event_id, heat_id, athlete_id, partner_athlete_id, display_name, partner_name, "
            "email, bib_number, division, age_category, volunteer_name, judge_pin, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled')",
            (nov_event_id, h_id, a_id, p_id, d_name, p_name, em, bib, div, age_c, vol, pin)
        )
        ensure_entry_splits(db, c.lastrowid)


# ── Serialization Helpers ───────────────────────────────────────────────────

def serialize_entry(db, entry_row, include_splits=True, include_history=False):
    e = dict(entry_row)
    div_key = e.get("division") or "men_open"
    div_info = HYROX_DIVISIONS.get(div_key, HYROX_DIVISIONS["men_open"])
    e["division_label"] = div_info["label"]
    e["division_short_label"] = div_info["short_label"]
    e["division_color"] = div_info["color"]
    e["is_doubles"] = div_info["is_doubles"]
    e["wall_ball_target_reps"] = div_info["wall_ball_target_reps"]
    e["full_display_name"] = (
        f"{e['display_name']} & {e['partner_name']}"
        if e.get("partner_name")
        else e["display_name"]
    )

    heat = None
    if e.get("heat_id"):
        heat = db.execute("SELECT * FROM hyrox_heats WHERE id=?", (e["heat_id"],)).fetchone()
    e["heat_name"] = heat["name"] if heat else "Unassigned"
    e["heat_start_time"] = heat["start_time"] if heat else "—"
    e["heat_number"] = heat["heat_number"] if heat else 0

    e["total_formatted"] = format_ms(e.get("total_ms"), include_hours=True)
    e["run_total_formatted"] = format_ms(e.get("run_total_ms"))
    e["station_total_formatted"] = format_ms(e.get("station_total_ms"))
    e["penalty_formatted"] = format_ms(e.get("penalty_ms")) if e.get("penalty_ms") else "00:00"

    if include_splits:
        ensure_entry_splits(db, e["id"])
        split_rows = db.execute(
            "SELECT * FROM hyrox_splits WHERE entry_id=? ORDER BY split_index ASC",
            (e["id"],)
        ).fetchall()
        splits = []
        completed_splits = 0
        current_split_index = None
        last_completed_split = None
        for sr in split_rows:
            sd = dict(sr)
            idx = sd["split_index"]
            presc = get_prescription_for_split(div_key, idx)
            sd["short_label"] = HYROX_SPLITS_TEMPLATE[idx - 1]["short_label"]
            sd["prescription"] = presc["prescription"]
            sd["distance"] = presc["distance"]
            sd["weight"] = presc["weight"]
            sd["duration_formatted"] = format_ms(sd.get("duration_ms"))
            if sd.get("duration_ms") is not None:
                completed_splits += 1
                last_completed_split = sd
            elif current_split_index is None:
                current_split_index = idx
            splits.append(sd)

        e["splits"] = splits
        e["completed_splits"] = completed_splits
        e["current_split_index"] = current_split_index if completed_splits < 16 else 16
        current_idx_for_card = current_split_index if current_split_index is not None else 16
        e["current_split_info"] = get_prescription_for_split(div_key, current_idx_for_card)
        e["next_split_info"] = (
            get_prescription_for_split(div_key, current_idx_for_card + 1)
            if current_idx_for_card < 16
            else None
        )
        e["last_completed_split"] = last_completed_split

        run_durations = [s["duration_ms"] for s in splits if s["split_type"] == "run" and s["duration_ms"] is not None]
        station_durations = [s["duration_ms"] for s in splits if s["split_type"] == "station" and s["duration_ms"] is not None]
        e["avg_run_ms"] = int(sum(run_durations) / len(run_durations)) if run_durations else None
        e["avg_run_formatted"] = format_ms(e["avg_run_ms"])
        e["avg_station_ms"] = int(sum(station_durations) / len(station_durations)) if station_durations else None
        e["avg_station_formatted"] = format_ms(e["avg_station_ms"])
        work_sum = (e.get("run_total_ms") or 0) + (e.get("station_total_ms") or 0)
        if work_sum > 0:
            e["run_pct"] = round(((e.get("run_total_ms") or 0) * 100.0) / work_sum, 1)
            e["station_pct"] = round(100.0 - e["run_pct"], 1)
        else:
            e["run_pct"] = 50.0
            e["station_pct"] = 50.0

    if include_history:
        e["history"] = build_athlete_history(db, e)

    return e


def build_athlete_history(db, current_entry_dict):
    """Build historical sim-over-sim comparison ('Roxfit-Lite') for this athlete."""
    athlete_id = current_entry_dict.get("athlete_id")
    display_name = (current_entry_dict.get("display_name") or "").strip().lower()
    email = (current_entry_dict.get("email") or "").strip().lower()

    if athlete_id:
        rows = db.execute(
            "SELECT e.*, ev.name as event_name, ev.event_date "
            "FROM hyrox_entries e JOIN hyrox_events ev ON ev.id = e.event_id "
            "WHERE e.athlete_id=? AND e.status='finished' "
            "ORDER BY ev.event_date ASC, e.id ASC",
            (athlete_id,)
        ).fetchall()
    elif email:
        rows = db.execute(
            "SELECT e.*, ev.name as event_name, ev.event_date "
            "FROM hyrox_entries e JOIN hyrox_events ev ON ev.id = e.event_id "
            "WHERE LOWER(e.email)=? AND e.status='finished' "
            "ORDER BY ev.event_date ASC, e.id ASC",
            (email,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT e.*, ev.name as event_name, ev.event_date "
            "FROM hyrox_entries e JOIN hyrox_events ev ON ev.id = e.event_id "
            "WHERE LOWER(e.display_name)=? AND e.status='finished' "
            "ORDER BY ev.event_date ASC, e.id ASC",
            (display_name,)
        ).fetchall()

    sims = []
    for r in rows:
        sr_list = db.execute(
            "SELECT split_index, split_type, station_key, label, duration_ms "
            "FROM hyrox_splits WHERE entry_id=? ORDER BY split_index ASC",
            (r["id"],)
        ).fetchall()
        split_map = {s["split_index"]: s["duration_ms"] for s in sr_list}
        sims.append({
            "entry_id": r["id"],
            "event_id": r["event_id"],
            "event_name": r["event_name"],
            "event_date": r["event_date"],
            "division": r["division"],
            "division_label": HYROX_DIVISIONS.get(r["division"], HYROX_DIVISIONS["men_open"])["label"],
            "total_ms": r["total_ms"],
            "total_formatted": format_ms(r["total_ms"], include_hours=True),
            "run_total_ms": r["run_total_ms"],
            "run_total_formatted": format_ms(r["run_total_ms"]),
            "station_total_ms": r["station_total_ms"],
            "station_total_formatted": format_ms(r["station_total_ms"]),
            "split_map": split_map,
        })

    prev_sim = None
    cur_id = current_entry_dict["id"]
    for idx, s in enumerate(sims):
        if s["entry_id"] == cur_id and idx > 0:
            prev_sim = sims[idx - 1]
            break
    if not prev_sim and sims and sims[-1]["entry_id"] != cur_id:
        prev_sim = sims[-1]

    comparison = None
    if prev_sim and current_entry_dict.get("splits"):
        total_delta = (
            (current_entry_dict["total_ms"] - prev_sim["total_ms"])
            if (current_entry_dict.get("total_ms") and prev_sim.get("total_ms"))
            else None
        )
        run_delta = (
            (current_entry_dict["run_total_ms"] - prev_sim["run_total_ms"])
            if (current_entry_dict.get("run_total_ms") and prev_sim.get("run_total_ms"))
            else None
        )
        station_delta = (
            (current_entry_dict["station_total_ms"] - prev_sim["station_total_ms"])
            if (current_entry_dict.get("station_total_ms") and prev_sim.get("station_total_ms"))
            else None
        )
        split_deltas = []
        for sp in current_entry_dict["splits"]:
            idx = sp["split_index"]
            cur_dur = sp.get("duration_ms")
            prev_dur = prev_sim["split_map"].get(idx)
            delta = (cur_dur - prev_dur) if (cur_dur is not None and prev_dur is not None) else None
            split_deltas.append({
                "split_index": idx,
                "label": sp["label"],
                "short_label": sp["short_label"],
                "split_type": sp["split_type"],
                "current_ms": cur_dur,
                "current_formatted": format_ms(cur_dur),
                "previous_ms": prev_dur,
                "previous_formatted": format_ms(prev_dur),
                "delta_ms": delta,
                "delta_formatted": format_delta_ms(delta),
                "improved": (delta < 0) if delta is not None else None,
            })
        comparison = {
            "previous_entry_id": prev_sim["entry_id"],
            "previous_event_name": prev_sim["event_name"],
            "previous_event_date": prev_sim["event_date"],
            "previous_total_ms": prev_sim["total_ms"],
            "previous_total_formatted": prev_sim["total_formatted"],
            "total_delta_ms": total_delta,
            "total_delta_formatted": format_delta_ms(total_delta),
            "run_delta_ms": run_delta,
            "run_delta_formatted": format_delta_ms(run_delta),
            "station_delta_ms": station_delta,
            "station_delta_formatted": format_delta_ms(station_delta),
            "split_deltas": split_deltas,
        }

    return {
        "sim_count": len(sims),
        "sims": sims,
        "comparison": comparison,
    }


def get_active_event_id(db, requested_event_id=None):
    ensure_hyrox_tables(db)
    if requested_event_id:
        row = db.execute("SELECT id FROM hyrox_events WHERE id=?", (requested_event_id,)).fetchone()
        if row:
            return row["id"]
    live = db.execute(
        "SELECT id FROM hyrox_events WHERE status='live' ORDER BY event_date DESC, id DESC LIMIT 1"
    ).fetchone()
    if live:
        return live["id"]
    latest = db.execute(
        "SELECT id FROM hyrox_events ORDER BY event_date DESC, id DESC LIMIT 1"
    ).fetchone()
    return latest["id"] if latest else None


# ── Page Routes (4 Surfaces) ────────────────────────────────────────────────

@hyrox_bp.route("/hyrox")
@hyrox_bp.route("/hyrox/admin")
def hyrox_admin_page():
    db = get_db()
    ensure_hyrox_tables(db)
    event_id = get_active_event_id(db, request.args.get("event_id", type=int))
    return render_template(
        "hyrox_admin.html",
        active_event_id=event_id,
        divisions=HYROX_DIVISIONS,
        age_categories=AGE_CATEGORIES,
        splits_template=HYROX_SPLITS_TEMPLATE,
    )


@hyrox_bp.route("/hyrox/judge")
def hyrox_judge_page():
    db = get_db()
    ensure_hyrox_tables(db)
    entry_id = request.args.get("entry", type=int) or request.args.get("entry_id", type=int)
    event_id = get_active_event_id(db, request.args.get("event_id", type=int))
    return render_template(
        "hyrox_judge.html",
        initial_entry_id=entry_id,
        active_event_id=event_id,
        divisions=HYROX_DIVISIONS,
        splits_template=HYROX_SPLITS_TEMPLATE,
    )


@hyrox_bp.route("/hyrox/tv")
def hyrox_tv_page():
    db = get_db()
    ensure_hyrox_tables(db)
    event_id = get_active_event_id(db, request.args.get("event_id", type=int))
    return render_template(
        "hyrox_tv.html",
        active_event_id=event_id,
        divisions=HYROX_DIVISIONS,
        splits_template=HYROX_SPLITS_TEMPLATE,
    )


@hyrox_bp.route("/hyrox/results/<int:entry_id>")
def hyrox_results_page(entry_id):
    db = get_db()
    ensure_hyrox_tables(db)
    row = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
    if not row:
        abort(404)
    event = db.execute("SELECT * FROM hyrox_events WHERE id=?", (row["event_id"],)).fetchone()
    entry_data = serialize_entry(db, row, include_splits=True, include_history=True)
    return render_template(
        "hyrox_results.html",
        entry=entry_data,
        event=dict(event) if event else {},
        divisions=HYROX_DIVISIONS,
        splits_template=HYROX_SPLITS_TEMPLATE,
    )


@hyrox_bp.route("/hyrox/athlete/<int:athlete_id>")
def hyrox_athlete_page(athlete_id):
    db = get_db()
    ensure_hyrox_tables(db)
    athlete = db.execute("SELECT * FROM hyrox_athletes WHERE id=?", (athlete_id,)).fetchone()
    if not athlete:
        abort(404)
    latest_entry = db.execute(
        "SELECT e.* FROM hyrox_entries e JOIN hyrox_events ev ON ev.id=e.event_id "
        "WHERE e.athlete_id=? ORDER BY (e.status='finished') DESC, ev.event_date DESC, e.id DESC LIMIT 1",
        (athlete_id,)
    ).fetchone()
    if not latest_entry:
        abort(404)
    event = db.execute("SELECT * FROM hyrox_events WHERE id=?", (latest_entry["event_id"],)).fetchone()
    entry_data = serialize_entry(db, latest_entry, include_splits=True, include_history=True)
    return render_template(
        "hyrox_results.html",
        entry=entry_data,
        athlete=dict(athlete),
        event=dict(event) if event else {},
        divisions=HYROX_DIVISIONS,
        splits_template=HYROX_SPLITS_TEMPLATE,
    )


# ── API: Standards & Sample TeamUp CSV ──────────────────────────────────────

@hyrox_bp.route("/api/hyrox/standards", methods=["GET"])
def api_hyrox_standards():
    return jsonify({
        "splits_template": HYROX_SPLITS_TEMPLATE,
        "divisions": HYROX_DIVISIONS,
        "age_categories": AGE_CATEGORIES,
    })


@hyrox_bp.route("/api/hyrox/sample-csv", methods=["GET"])
def api_hyrox_sample_csv():
    sample_rows = [
        ["First Name", "Last Name", "Email", "DOB", "Age Category", "Division", "Partner Name", "Heat Time", "Bib", "Volunteer"],
        ["Ewan", "Taylor", "taylor.ewan@googlemail.com", "1989-04-12", "35-39", "Men Open", "", "08:00", "101", "Coach Chris"],
        ["Sarah", "Jenkins", "sarah.jenkins@example.com", "1993-02-15", "30-34", "Women Open", "", "08:00", "103", "Sam Walker"],
        ["Laura", "Mitchell", "laura.mitchell@example.com", "1992-11-03", "30-34", "Women Pro", "", "08:15", "104", "Jamie Ross"],
        ["Callum", "Fraser", "callum.fraser@example.com", "1998-01-10", "25-29", "Men Pro", "", "08:15", "105", "Alex Reid"],
        ["Chris", "Smith", "chris.smith@example.com", "1988-06-19", "35-39", "Mixed Doubles", "Emma Wallace", "08:30", "201", "Katie Bell"],
        ["Kirsty", "Grant", "kirsty.grant@example.com", "1994-05-14", "30-34", "Women Doubles", "Megan Scott", "08:30", "202", "Sam Walker"],
        ["Dave", "Kerr", "dave.kerr@example.com", "1987-10-08", "35-39", "Men Doubles", "Mark Stewart", "08:45", "203", "Coach Chris"],
    ]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(sample_rows)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="teamup_hyrox_sample.csv"'},
    )


# ── API: Events & Heats ─────────────────────────────────────────────────────

@hyrox_bp.route("/api/hyrox/events", methods=["GET"])
def api_list_events():
    db = get_db()
    ensure_hyrox_tables(db)
    rows = db.execute("SELECT * FROM hyrox_events ORDER BY event_date DESC, id DESC").fetchall()
    result = []
    for r in rows:
        ev = dict(r)
        counts = db.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN status='racing' THEN 1 ELSE 0 END) as racing, "
            "SUM(CASE WHEN status='finished' THEN 1 ELSE 0 END) as finished, "
            "SUM(CASE WHEN status='scheduled' THEN 1 ELSE 0 END) as scheduled "
            "FROM hyrox_entries WHERE event_id=?",
            (r["id"],)
        ).fetchone()
        ev["entry_count"] = counts["total"] or 0
        ev["racing_count"] = counts["racing"] or 0
        ev["finished_count"] = counts["finished"] or 0
        ev["scheduled_count"] = counts["scheduled"] or 0
        result.append(ev)
    return jsonify(result)


@hyrox_bp.route("/api/hyrox/events", methods=["POST"])
def api_create_event():
    db = get_db()
    ensure_hyrox_tables(db)
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Event name is required"}), 400
    event_date = (data.get("event_date") or datetime.now().strftime("%Y-%m-%d")).strip()
    venue = (data.get("venue") or "CS Performance Studio").strip()
    wave_interval_mins = int(data.get("wave_interval_mins") or 15)
    lanes_per_wave = int(data.get("lanes_per_wave") or 4)
    status = (data.get("status") or "live").strip()
    notes = (data.get("notes") or "").strip()

    cur = db.execute(
        "INSERT INTO hyrox_events (name, event_date, venue, wave_interval_mins, lanes_per_wave, status, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, event_date, venue, wave_interval_mins, lanes_per_wave, status, notes)
    )
    event_id = cur.lastrowid

    num_waves = int(data.get("num_waves") or 4)
    first_wave_time = (data.get("first_wave_time") or "08:00").strip()
    if num_waves > 0:
        _generate_heats_for_event(db, event_id, first_wave_time, num_waves, wave_interval_mins, lanes_per_wave)

    db.commit()
    ev = db.execute("SELECT * FROM hyrox_events WHERE id=?", (event_id,)).fetchone()
    return jsonify(dict(ev)), 201


@hyrox_bp.route("/api/hyrox/events/<int:event_id>", methods=["PUT"])
def api_update_event(event_id):
    db = get_db()
    ensure_hyrox_tables(db)
    ev = db.execute("SELECT * FROM hyrox_events WHERE id=?", (event_id,)).fetchone()
    if not ev:
        return jsonify({"error": "Event not found"}), 404
    data = request.get_json(force=True) or {}
    db.execute(
        "UPDATE hyrox_events SET name=?, event_date=?, venue=?, wave_interval_mins=?, lanes_per_wave=?, status=?, notes=? WHERE id=?",
        (
            data.get("name", ev["name"]),
            data.get("event_date", ev["event_date"]),
            data.get("venue", ev["venue"]),
            int(data.get("wave_interval_mins", ev["wave_interval_mins"])),
            int(data.get("lanes_per_wave", ev["lanes_per_wave"])),
            data.get("status", ev["status"]),
            data.get("notes", ev["notes"]),
            event_id,
        ),
    )
    db.commit()
    updated = db.execute("SELECT * FROM hyrox_events WHERE id=?", (event_id,)).fetchone()
    return jsonify(dict(updated))


def _generate_heats_for_event(db, event_id, start_time_str, count, interval_mins, max_lanes):
    try:
        parts = [int(p) for p in start_time_str.split(":")]
        start_total_mins = parts[0] * 60 + parts[1]
    except Exception:
        start_total_mins = 8 * 60

    existing_max = db.execute(
        "SELECT COALESCE(MAX(heat_number), 0) as m FROM hyrox_heats WHERE event_id=?",
        (event_id,)
    ).fetchone()["m"]

    created = []
    for i in range(count):
        heat_num = existing_max + i + 1
        t_mins = start_total_mins + i * interval_mins
        hh = (t_mins // 60) % 24
        mm = t_mins % 60
        t_str = f"{hh:02d}:{mm:02d}"
        h_name = f"Wave {heat_num} — {t_str}"
        cur = db.execute(
            "INSERT INTO hyrox_heats (event_id, heat_number, name, start_time, max_lanes, status) "
            "VALUES (?, ?, ?, ?, ?, 'scheduled')",
            (event_id, heat_num, h_name, t_str, max_lanes)
        )
        created.append(cur.lastrowid)
    return created


@hyrox_bp.route("/api/hyrox/events/<int:event_id>/heats", methods=["POST"])
def api_create_or_generate_heats(event_id):
    db = get_db()
    ensure_hyrox_tables(db)
    data = request.get_json(force=True) or {}
    if data.get("generate_batch"):
        start_time = (data.get("start_time") or "08:00").strip()
        count = int(data.get("count") or 4)
        interval_mins = int(data.get("interval_mins") or 15)
        max_lanes = int(data.get("max_lanes") or 4)
        _generate_heats_for_event(db, event_id, start_time, count, interval_mins, max_lanes)
        db.commit()
    else:
        existing_max = db.execute(
            "SELECT COALESCE(MAX(heat_number), 0) as m FROM hyrox_heats WHERE event_id=?",
            (event_id,)
        ).fetchone()["m"]
        heat_num = int(data.get("heat_number") or (existing_max + 1))
        start_time = (data.get("start_time") or "08:00").strip()
        name = (data.get("name") or f"Wave {heat_num} — {start_time}").strip()
        max_lanes = int(data.get("max_lanes") or 4)
        db.execute(
            "INSERT INTO hyrox_heats (event_id, heat_number, name, start_time, max_lanes, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, heat_num, name, start_time, max_lanes, data.get("status", "scheduled"))
        )
        db.commit()

    heats = db.execute(
        "SELECT * FROM hyrox_heats WHERE event_id=? ORDER BY start_time ASC, heat_number ASC",
        (event_id,)
    ).fetchall()
    return jsonify([dict(h) for h in heats]), 201


@hyrox_bp.route("/api/hyrox/heats/<int:heat_id>", methods=["PUT", "DELETE"])
def api_modify_heat(heat_id):
    db = get_db()
    ensure_hyrox_tables(db)
    heat = db.execute("SELECT * FROM hyrox_heats WHERE id=?", (heat_id,)).fetchone()
    if not heat:
        return jsonify({"error": "Heat not found"}), 404
    if request.method == "DELETE":
        db.execute("UPDATE hyrox_entries SET heat_id=NULL WHERE heat_id=?", (heat_id,))
        db.execute("DELETE FROM hyrox_heats WHERE id=?", (heat_id,))
        db.commit()
        return jsonify({"ok": True})
    data = request.get_json(force=True) or {}
    db.execute(
        "UPDATE hyrox_heats SET heat_number=?, name=?, start_time=?, max_lanes=?, status=? WHERE id=?",
        (
            int(data.get("heat_number", heat["heat_number"])),
            data.get("name", heat["name"]),
            data.get("start_time", heat["start_time"]),
            int(data.get("max_lanes", heat["max_lanes"])),
            data.get("status", heat["status"]),
            heat_id,
        )
    )
    db.commit()
    updated = db.execute("SELECT * FROM hyrox_heats WHERE id=?", (heat_id,)).fetchone()
    return jsonify(dict(updated))


@hyrox_bp.route("/api/hyrox/events/<int:event_id>/state", methods=["GET"])
def api_event_state(event_id):
    db = get_db()
    ensure_hyrox_tables(db)
    ev = db.execute("SELECT * FROM hyrox_events WHERE id=?", (event_id,)).fetchone()
    if not ev:
        return jsonify({"error": "Event not found"}), 404

    heats = [
        dict(h)
        for h in db.execute(
            "SELECT * FROM hyrox_heats WHERE event_id=? ORDER BY start_time ASC, heat_number ASC",
            (event_id,)
        ).fetchall()
    ]
    entry_rows = db.execute(
        "SELECT * FROM hyrox_entries WHERE event_id=? ORDER BY id ASC",
        (event_id,)
    ).fetchall()
    entries = [serialize_entry(db, r, include_splits=True, include_history=True) for r in entry_rows]

    entries.sort(key=lambda x: (x.get("heat_start_time") or "99:99", x.get("bib_number") or "999", x["id"]))

    for h in heats:
        h["entries"] = [e for e in entries if e.get("heat_id") == h["id"]]
        h["assigned_lanes"] = len(h["entries"])

    leaderboards = {}
    for div_key, div_meta in HYROX_DIVISIONS.items():
        finished_in_div = [
            e for e in entries
            if e["division"] == div_key and e["status"] == "finished" and e.get("total_ms") is not None
        ]
        finished_in_div.sort(key=lambda x: x["total_ms"])
        for rank_idx, fin_e in enumerate(finished_in_div, start=1):
            fin_e["division_rank"] = rank_idx
        leaderboards[div_key] = {
            "division": div_key,
            "label": div_meta["label"],
            "short_label": div_meta["short_label"],
            "color": div_meta["color"],
            "entries": finished_in_div,
        }

    racing_entries = [e for e in entries if e["status"] == "racing"]
    scheduled_entries = [e for e in entries if e["status"] == "scheduled"]
    finished_entries = [e for e in entries if e["status"] == "finished"]
    finished_entries.sort(key=lambda x: x["total_ms"] if x.get("total_ms") is not None else 999999999)

    return jsonify({
        "server_time_ms": int(time.time() * 1000),
        "event": dict(ev),
        "heats": heats,
        "entries": entries,
        "racing_entries": racing_entries,
        "scheduled_entries": scheduled_entries,
        "finished_entries": finished_entries,
        "leaderboards": leaderboards,
        "divisions": HYROX_DIVISIONS,
        "age_categories": AGE_CATEGORIES,
        "splits_template": HYROX_SPLITS_TEMPLATE,
    })


# ── API: Entries & TeamUp CSV Import ────────────────────────────────────────

def _create_entry_record(db, event_id, payload):
    display_name = (payload.get("display_name") or payload.get("full_name") or "").strip()
    if not display_name:
        first = (payload.get("first_name") or "").strip()
        last = (payload.get("last_name") or "").strip()
        display_name = f"{first} {last}".strip()
    if not display_name:
        return None, "Athlete name is required"

    partner_name = (payload.get("partner_name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    dob = (payload.get("dob") or "").strip()
    age_cat = normalize_age_category(payload.get("age_category") or dob or "30-34")
    division = normalize_division(payload.get("division") or ("mixed_doubles" if partner_name else "men_open"))
    volunteer_name = (payload.get("volunteer_name") or payload.get("volunteer") or "").strip()
    notes = (payload.get("notes") or "").strip()

    heat_id = payload.get("heat_id")
    heat_time = (payload.get("heat_time") or payload.get("wave_time") or "").strip()
    if heat_id:
        heat_id = int(heat_id)
    elif heat_time:
        h_row = db.execute(
            "SELECT id FROM hyrox_heats WHERE event_id=? AND (start_time=? OR name LIKE ?) LIMIT 1",
            (event_id, heat_time, f"%{heat_time}%")
        ).fetchone()
        if h_row:
            heat_id = h_row["id"]
        else:
            existing_max = db.execute(
                "SELECT COALESCE(MAX(heat_number), 0) as m FROM hyrox_heats WHERE event_id=?",
                (event_id,)
            ).fetchone()["m"]
            h_num = existing_max + 1
            cur_h = db.execute(
                "INSERT INTO hyrox_heats (event_id, heat_number, name, start_time, max_lanes, status) "
                "VALUES (?, ?, ?, ?, 4, 'scheduled')",
                (event_id, h_num, f"Wave {h_num} — {heat_time}", heat_time)
            )
            heat_id = cur_h.lastrowid

    bib_number = str(payload.get("bib_number") or payload.get("bib") or "").strip()
    if not bib_number:
        cnt = db.execute("SELECT COUNT(*) as c FROM hyrox_entries WHERE event_id=?", (event_id,)).fetchone()["c"]
        bib_number = str(101 + cnt)

    judge_pin = _generate_unique_pin(db, event_id, str(payload.get("judge_pin") or "").strip() or None)

    athlete_id = find_or_create_athlete(
        db,
        full_name=display_name,
        email=email,
        dob=dob,
        age_category=age_cat,
        teamup_customer_id=str(payload.get("teamup_customer_id") or ""),
    )
    partner_athlete_id = (
        find_or_create_athlete(db, full_name=partner_name, age_category=age_cat)
        if partner_name
        else None
    )

    cur = db.execute(
        "INSERT INTO hyrox_entries (event_id, heat_id, athlete_id, partner_athlete_id, display_name, partner_name, "
        "email, bib_number, division, age_category, volunteer_name, judge_pin, status, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled', ?)",
        (
            event_id,
            heat_id,
            athlete_id,
            partner_athlete_id,
            display_name,
            partner_name,
            email,
            bib_number,
            division,
            age_cat,
            volunteer_name,
            judge_pin,
            notes,
        ),
    )
    entry_id = cur.lastrowid
    ensure_entry_splits(db, entry_id)
    return entry_id, None


@hyrox_bp.route("/api/hyrox/events/<int:event_id>/entries", methods=["POST"])
def api_create_entry(event_id):
    db = get_db()
    ensure_hyrox_tables(db)
    data = request.get_json(force=True) or {}
    entry_id, err = _create_entry_record(db, event_id, data)
    if err:
        return jsonify({"error": err}), 400
    db.commit()
    row = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
    return jsonify(serialize_entry(db, row, include_splits=True, include_history=True)), 201


def _auto_map_csv_row(raw_row, custom_map=None):
    custom_map = custom_map or {}
    norm = {}
    for k, v in raw_row.items():
        if k is None:
            continue
        ck = re.sub(r"[^a-z0-9]+", "_", str(k).strip().lower()).strip("_")
        norm[ck] = (str(v).strip() if v is not None else "")

    def _pick(field_name, aliases):
        mapped_col = custom_map.get(field_name)
        if mapped_col and mapped_col in raw_row:
            return str(raw_row[mapped_col] or "").strip()
        for al in aliases:
            if al in norm and norm[al]:
                return norm[al]
        return ""

    full_name = _pick("display_name", ["name", "full_name", "athlete", "athlete_name", "client_name", "customer_name", "member_name", "display_name"])
    first_name = _pick("first_name", ["first_name", "firstname", "given_name", "first"])
    last_name = _pick("last_name", ["last_name", "lastname", "surname", "family_name", "last"])
    if not full_name and (first_name or last_name):
        full_name = f"{first_name} {last_name}".strip()

    return {
        "display_name": full_name,
        "email": _pick("email", ["email", "email_address", "customer_email", "e_mail"]),
        "dob": _pick("dob", ["dob", "date_of_birth", "birth_date", "birthdate"]),
        "age_category": _pick("age_category", ["age_category", "age_group", "age", "age_cat", "category_age"]),
        "division": _pick("division", ["division", "category", "race_division", "hyrox_division", "ticket_type", "class_type", "membership"]),
        "partner_name": _pick("partner_name", ["partner_name", "partner", "doubles_partner", "teammate", "athlete_2"]),
        "heat_time": _pick("heat_time", ["heat_time", "wave_time", "start_time", "heat", "wave", "time_slot", "session_time"]),
        "bib_number": _pick("bib_number", ["bib", "bib_number", "race_number", "number"]),
        "volunteer_name": _pick("volunteer_name", ["volunteer", "volunteer_name", "judge", "judge_name", "lane_judge"]),
        "teamup_customer_id": _pick("teamup_customer_id", ["customer_id", "teamup_id", "teamup_customer_id", "member_id"]),
    }


@hyrox_bp.route("/api/hyrox/events/<int:event_id>/import-csv", methods=["POST"])
def api_import_csv(event_id):
    db = get_db()
    ensure_hyrox_tables(db)
    ev = db.execute("SELECT * FROM hyrox_events WHERE id=?", (event_id,)).fetchone()
    if not ev:
        return jsonify({"error": "Event not found"}), 404

    csv_text = ""
    custom_map = {}
    rows_input = None

    if request.files and "file" in request.files:
        f = request.files["file"]
        csv_text = f.read().decode("utf-8-sig", errors="replace")
    else:
        data = request.get_json(silent=True) or {}
        csv_text = data.get("csv_text") or ""
        custom_map = data.get("column_map") or {}
        rows_input = data.get("rows")

    parsed_rows = []
    if isinstance(rows_input, list):
        parsed_rows = rows_input
    elif csv_text.strip():
        reader = csv.DictReader(io.StringIO(csv_text.strip()))
        parsed_rows = list(reader)
    else:
        return jsonify({"error": "No CSV content provided"}), 400

    imported_ids = []
    skipped = 0
    for raw_r in parsed_rows:
        mapped = _auto_map_csv_row(raw_r, custom_map=custom_map)
        if not mapped.get("display_name"):
            skipped += 1
            continue
        eid, err = _create_entry_record(db, event_id, mapped)
        if eid:
            imported_ids.append(eid)
        else:
            skipped += 1

    db.commit()
    return jsonify({
        "ok": True,
        "imported_count": len(imported_ids),
        "skipped_count": skipped,
        "imported_entry_ids": imported_ids,
    })


@hyrox_bp.route("/api/hyrox/entries/<int:entry_id>", methods=["GET", "PUT", "DELETE"])
def api_entry_detail(entry_id):
    db = get_db()
    ensure_hyrox_tables(db)
    row = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
    if not row:
        return jsonify({"error": "Entry not found"}), 404

    if request.method == "GET":
        return jsonify({
            "server_time_ms": int(time.time() * 1000),
            "entry": serialize_entry(db, row, include_splits=True, include_history=True),
        })

    if request.method == "DELETE":
        db.execute("DELETE FROM hyrox_entries WHERE id=?", (entry_id,))
        db.commit()
        return jsonify({"ok": True})

    data = request.get_json(force=True) or {}
    new_heat_id = data.get("heat_id", row["heat_id"])
    if new_heat_id == "" or new_heat_id == 0:
        new_heat_id = None
    elif new_heat_id is not None:
        new_heat_id = int(new_heat_id)

    new_division = normalize_division(data.get("division", row["division"]))
    new_age_cat = normalize_age_category(data.get("age_category", row["age_category"]))
    new_display_name = (data.get("display_name", row["display_name"]) or "").strip()
    new_partner_name = (data.get("partner_name", row["partner_name"]) or "").strip()
    new_email = (data.get("email", row["email"]) or "").strip().lower()
    new_bib = str(data.get("bib_number", row["bib_number"]) or "").strip()
    new_volunteer = (data.get("volunteer_name", row["volunteer_name"]) or "").strip()
    new_pin = str(data.get("judge_pin", row["judge_pin"]) or "").strip()
    new_status = (data.get("status", row["status"]) or "scheduled").strip()
    new_notes = (data.get("notes", row["notes"]) or "").strip()

    if "penalty_ms" in data or "penalty_str" in data:
        p_val = data.get("penalty_ms") if "penalty_ms" in data else data.get("penalty_str")
        new_penalty = parse_duration_to_ms(p_val) or 0
    else:
        new_penalty = int(row["penalty_ms"] or 0)

    same_heat_volunteer_warning = None
    if new_volunteer and new_heat_id:
        conflict = db.execute(
            "SELECT display_name, bib_number FROM hyrox_entries "
            "WHERE event_id=? AND heat_id=? AND LOWER(volunteer_name)=? AND id!=? LIMIT 1",
            (row["event_id"], new_heat_id, new_volunteer.lower(), entry_id)
        ).fetchone()
        if conflict:
            same_heat_volunteer_warning = (
                f"{new_volunteer} is also assigned to #{conflict['bib_number']} {conflict['display_name']} in this same wave."
            )

    db.execute(
        "UPDATE hyrox_entries SET heat_id=?, display_name=?, partner_name=?, email=?, bib_number=?, "
        "division=?, age_category=?, volunteer_name=?, judge_pin=?, status=?, penalty_ms=?, notes=?, "
        "updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (
            new_heat_id,
            new_display_name,
            new_partner_name,
            new_email,
            new_bib,
            new_division,
            new_age_cat,
            new_volunteer,
            new_pin,
            new_status,
            new_penalty,
            new_notes,
            entry_id,
        ),
    )
    recalculate_entry_totals(db, entry_id)
    db.commit()

    updated = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
    payload = serialize_entry(db, updated, include_splits=True, include_history=True)
    if same_heat_volunteer_warning:
        payload["volunteer_warning"] = same_heat_volunteer_warning
    return jsonify(payload)


# ── API: Volunteer Mobile Judge Timing & Split Corrections ──────────────────

@hyrox_bp.route("/api/hyrox/judge/lookup", methods=["POST"])
def api_judge_lookup():
    db = get_db()
    ensure_hyrox_tables(db)
    data = request.get_json(force=True) or {}
    pin = str(data.get("judge_pin") or data.get("pin") or "").strip()
    entry_id = data.get("entry_id")
    event_id = data.get("event_id")

    row = None
    if entry_id:
        row = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (int(entry_id),)).fetchone()
    elif pin:
        if event_id:
            row = db.execute(
                "SELECT * FROM hyrox_entries WHERE event_id=? AND judge_pin=? LIMIT 1",
                (int(event_id), pin)
            ).fetchone()
        if not row:
            row = db.execute(
                "SELECT * FROM hyrox_entries WHERE judge_pin=? ORDER BY id DESC LIMIT 1",
                (pin,)
            ).fetchone()
    if not row:
        return jsonify({"error": "No athlete entry found for that Judge PIN"}), 404

    return jsonify({
        "ok": True,
        "entry": serialize_entry(db, row, include_splits=True, include_history=False),
    })


@hyrox_bp.route("/api/hyrox/entries/<int:entry_id>/start", methods=["POST"])
def api_start_entry(entry_id):
    db = get_db()
    ensure_hyrox_tables(db)
    row = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
    if not row:
        return jsonify({"error": "Entry not found"}), 404

    data = request.get_json(silent=True) or {}
    now_ms = int(data.get("started_at_ms") or (time.time() * 1000))

    ensure_entry_splits(db, entry_id)
    if not row["started_at_ms"] or data.get("force"):
        db.execute(
            "UPDATE hyrox_entries SET status='racing', started_at_ms=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (now_ms, entry_id)
        )
    else:
        db.execute(
            "UPDATE hyrox_entries SET status='racing', updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (entry_id,)
        )
    if row["heat_id"]:
        db.execute("UPDATE hyrox_heats SET status='racing' WHERE id=? AND status='scheduled'", (row["heat_id"],))
    db.commit()

    updated = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
    return jsonify({
        "ok": True,
        "server_time_ms": int(time.time() * 1000),
        "entry": serialize_entry(db, updated, include_splits=True, include_history=False),
    })


@hyrox_bp.route("/api/hyrox/entries/<int:entry_id>/advance", methods=["POST"])
def api_advance_split(entry_id):
    db = get_db()
    ensure_hyrox_tables(db)
    row = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
    if not row:
        return jsonify({"error": "Entry not found"}), 404

    ensure_entry_splits(db, entry_id)
    data = request.get_json(silent=True) or {}
    now_ms = int(data.get("timestamp_ms") or data.get("completed_at_ms") or (time.time() * 1000))

    if not row["started_at_ms"]:
        db.execute(
            "UPDATE hyrox_entries SET status='racing', started_at_ms=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (now_ms, entry_id)
        )
        db.commit()
        updated = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
        return jsonify({
            "ok": True,
            "action": "started",
            "server_time_ms": int(time.time() * 1000),
            "entry": serialize_entry(db, updated, include_splits=True, include_history=False),
        })

    splits = db.execute(
        "SELECT * FROM hyrox_splits WHERE entry_id=? ORDER BY split_index ASC",
        (entry_id,)
    ).fetchall()

    target_split_index = data.get("split_index")
    target_split = None
    if target_split_index:
        for s in splits:
            if s["split_index"] == int(target_split_index):
                target_split = s
                break
    else:
        for s in splits:
            if s["duration_ms"] is None:
                target_split = s
                break

    if not target_split:
        recalculate_entry_totals(db, entry_id)
        db.commit()
        updated = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
        return jsonify({
            "ok": True,
            "action": "already_finished",
            "entry": serialize_entry(db, updated, include_splits=True, include_history=False),
        })

    idx = target_split["split_index"]
    explicit_duration = parse_duration_to_ms(data.get("duration_ms"))
    if explicit_duration is not None and explicit_duration >= 0:
        duration_ms = explicit_duration
    else:
        prev_completed_ms = row["started_at_ms"]
        for s in splits:
            if s["split_index"] < idx:
                if s["completed_at_ms"]:
                    prev_completed_ms = s["completed_at_ms"]
                elif s["duration_ms"]:
                    prev_completed_ms += s["duration_ms"]
        duration_ms = max(1000, now_ms - int(prev_completed_ms))

    db.execute(
        "UPDATE hyrox_splits SET duration_ms=?, completed_at_ms=?, edited_by=? WHERE entry_id=? AND split_index=?",
        (duration_ms, now_ms, data.get("edited_by", "volunteer"), entry_id, idx)
    )
    recalculate_entry_totals(db, entry_id)
    db.commit()

    updated = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
    return jsonify({
        "ok": True,
        "action": "finished" if idx == 16 else "split_completed",
        "completed_split_index": idx,
        "server_time_ms": int(time.time() * 1000),
        "entry": serialize_entry(db, updated, include_splits=True, include_history=False),
    })


@hyrox_bp.route("/api/hyrox/entries/<int:entry_id>/undo", methods=["POST"])
def api_undo_last_split(entry_id):
    db = get_db()
    ensure_hyrox_tables(db)
    row = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
    if not row:
        return jsonify({"error": "Entry not found"}), 404

    ensure_entry_splits(db, entry_id)
    last_done = db.execute(
        "SELECT * FROM hyrox_splits WHERE entry_id=? AND duration_ms IS NOT NULL ORDER BY split_index DESC LIMIT 1",
        (entry_id,)
    ).fetchone()

    if last_done:
        db.execute(
            "UPDATE hyrox_splits SET duration_ms=NULL, completed_at_ms=NULL WHERE id=?",
            (last_done["id"],)
        )
        db.execute(
            "UPDATE hyrox_entries SET status='racing', finished_at_ms=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (entry_id,)
        )
        recalculate_entry_totals(db, entry_id)
        undone_index = last_done["split_index"]
    else:
        db.execute(
            "UPDATE hyrox_entries SET status='scheduled', started_at_ms=NULL, finished_at_ms=NULL, "
            "total_ms=NULL, run_total_ms=NULL, station_total_ms=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (entry_id,)
        )
        undone_index = 0

    db.commit()
    updated = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
    return jsonify({
        "ok": True,
        "undone_split_index": undone_index,
        "server_time_ms": int(time.time() * 1000),
        "entry": serialize_entry(db, updated, include_splits=True, include_history=False),
    })


@hyrox_bp.route("/api/hyrox/entries/<int:entry_id>/wall-balls", methods=["POST"])
def api_update_wall_balls(entry_id):
    db = get_db()
    ensure_hyrox_tables(db)
    row = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
    if not row:
        return jsonify({"error": "Entry not found"}), 404

    data = request.get_json(force=True) or {}
    current_reps = int(row["wall_ball_reps"] or 0)
    if "reps" in data:
        new_reps = max(0, int(data["reps"]))
    elif "delta" in data:
        new_reps = max(0, current_reps + int(data["delta"]))
    else:
        new_reps = current_reps

    db.execute(
        "UPDATE hyrox_entries SET wall_ball_reps=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (new_reps, entry_id)
    )
    db.commit()
    div_info = HYROX_DIVISIONS.get(row["division"], HYROX_DIVISIONS["men_open"])
    return jsonify({
        "ok": True,
        "wall_ball_reps": new_reps,
        "wall_ball_target_reps": div_info["wall_ball_target_reps"],
    })


@hyrox_bp.route("/api/hyrox/entries/<int:entry_id>/reset", methods=["POST"])
def api_reset_entry_timer(entry_id):
    db = get_db()
    ensure_hyrox_tables(db)
    row = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
    if not row:
        return jsonify({"error": "Entry not found"}), 404

    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "reset")
    if mode == "reopen":
        db.execute(
            "UPDATE hyrox_entries SET status='racing', finished_at_ms=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (entry_id,)
        )
        recalculate_entry_totals(db, entry_id)
    else:
        db.execute(
            "UPDATE hyrox_splits SET duration_ms=NULL, completed_at_ms=NULL, edited_by='', notes='' WHERE entry_id=?",
            (entry_id,)
        )
        db.execute(
            "UPDATE hyrox_entries SET status='scheduled', started_at_ms=NULL, finished_at_ms=NULL, "
            "total_ms=NULL, run_total_ms=NULL, station_total_ms=NULL, penalty_ms=0, wall_ball_reps=0, "
            "updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (entry_id,)
        )
    db.commit()
    updated = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
    return jsonify({
        "ok": True,
        "entry": serialize_entry(db, updated, include_splits=True, include_history=True),
    })


@hyrox_bp.route("/api/hyrox/entries/<int:entry_id>/splits", methods=["PUT", "POST"])
def api_edit_entry_splits(entry_id):
    db = get_db()
    ensure_hyrox_tables(db)
    row = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
    if not row:
        return jsonify({"error": "Entry not found"}), 404

    ensure_entry_splits(db, entry_id)
    data = request.get_json(force=True) or {}
    edited_by = (data.get("edited_by") or "director").strip()

    if data.get("split_combined"):
        sc = data["split_combined"]
        idx_a = int(sc.get("first_split_index") or sc.get("from_split_index"))
        idx_b = int(sc.get("second_split_index") or sc.get("to_split_index") or (idx_a + 1))
        sp_a = db.execute(
            "SELECT * FROM hyrox_splits WHERE entry_id=? AND split_index=?",
            (entry_id, idx_a)
        ).fetchone()
        sp_b = db.execute(
            "SELECT * FROM hyrox_splits WHERE entry_id=? AND split_index=?",
            (entry_id, idx_b)
        ).fetchone()
        if sp_a and sp_b:
            combined_ms = int((sp_a["duration_ms"] or 0) + (sp_b["duration_ms"] or 0))
            if "combined_duration_ms" in sc or "combined_duration_str" in sc:
                c_override = parse_duration_to_ms(sc.get("combined_duration_ms") or sc.get("combined_duration_str"))
                if c_override:
                    combined_ms = c_override
            first_ms = parse_duration_to_ms(sc.get("first_duration_ms") or sc.get("first_duration_str"))
            if first_ms is None:
                ratio = float(sc.get("ratio", 0.5))
                first_ms = int(round(combined_ms * ratio))
            second_ms = max(0, combined_ms - first_ms)
            db.execute(
                "UPDATE hyrox_splits SET duration_ms=?, edited_by=?, notes=? WHERE entry_id=? AND split_index=?",
                (first_ms, edited_by, "Split from combined segment", entry_id, idx_a)
            )
            db.execute(
                "UPDATE hyrox_splits SET duration_ms=?, edited_by=?, notes=? WHERE entry_id=? AND split_index=?",
                (second_ms, edited_by, "Split from combined segment", entry_id, idx_b)
            )

    if "split_index" in data and ("duration_ms" in data or "duration_str" in data):
        s_idx = int(data["split_index"])
        raw_d = data.get("duration_ms") if "duration_ms" in data else data.get("duration_str")
        dur_ms = parse_duration_to_ms(raw_d)
        db.execute(
            "UPDATE hyrox_splits SET duration_ms=?, edited_by=?, notes=? WHERE entry_id=? AND split_index=?",
            (dur_ms, edited_by, data.get("notes", ""), entry_id, s_idx)
        )

    if isinstance(data.get("splits"), list):
        for item in data["splits"]:
            s_idx = int(item["split_index"])
            if "clear" in item and item["clear"]:
                dur_ms = None
            else:
                raw_d = item.get("duration_ms") if "duration_ms" in item else item.get("duration_str")
                dur_ms = parse_duration_to_ms(raw_d)
            db.execute(
                "UPDATE hyrox_splits SET duration_ms=?, edited_by=?, notes=? WHERE entry_id=? AND split_index=?",
                (dur_ms, edited_by, item.get("notes", ""), entry_id, s_idx)
            )

    if "penalty_ms" in data or "penalty_str" in data:
        raw_p = data.get("penalty_ms") if "penalty_ms" in data else data.get("penalty_str")
        pen_ms = parse_duration_to_ms(raw_p) or 0
        db.execute("UPDATE hyrox_entries SET penalty_ms=? WHERE id=?", (pen_ms, entry_id))

    if "status" in data and data["status"] in ("scheduled", "racing", "finished", "dns", "dnf"):
        db.execute("UPDATE hyrox_entries SET status=? WHERE id=?", (data["status"], entry_id))

    recalculate_entry_totals(db, entry_id)
    db.commit()

    updated = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
    return jsonify({
        "ok": True,
        "entry": serialize_entry(db, updated, include_splits=True, include_history=True),
    })


@hyrox_bp.route("/api/hyrox/athletes/<int:athlete_id>/history", methods=["GET"])
def api_athlete_history(athlete_id):
    db = get_db()
    ensure_hyrox_tables(db)
    athlete = db.execute("SELECT * FROM hyrox_athletes WHERE id=?", (athlete_id,)).fetchone()
    if not athlete:
        return jsonify({"error": "Athlete not found"}), 404
    latest = db.execute(
        "SELECT * FROM hyrox_entries WHERE athlete_id=? ORDER BY id DESC LIMIT 1",
        (athlete_id,)
    ).fetchone()
    if not latest:
        return jsonify({"athlete": dict(athlete), "history": {"sim_count": 0, "sims": [], "comparison": None}})
    entry_dict = serialize_entry(db, latest, include_splits=True, include_history=True)
    return jsonify({
        "athlete": dict(athlete),
        "latest_entry": entry_dict,
        "history": entry_dict["history"],
    })
