import csv
import io
import json
import os
import random
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, date
from flask import Blueprint, jsonify, render_template, request, Response, abort
from database import get_db

hyrox_bp = Blueprint("hyrox", __name__)

# ── 16-Split Sequence (No Roxzone — Extended Run Loop, 1.2 km per Run) ──────

HYROX_RUN_DISTANCE_KM = 1.2

HYROX_SPLITS_TEMPLATE = [
    {"split_index": 1,  "split_type": "run",     "station_key": "run_1",          "label": "Run 1 (1.2 km)",               "short_label": "R1"},
    {"split_index": 2,  "split_type": "station", "station_key": "skierg",         "label": "1. SkiErg (1,000m)",           "short_label": "S1 SkiErg"},
    {"split_index": 3,  "split_type": "run",     "station_key": "run_2",          "label": "Run 2 (1.2 km)",               "short_label": "R2"},
    {"split_index": 4,  "split_type": "station", "station_key": "sled_push",      "label": "2. Sled Push (50m)",           "short_label": "S2 Push"},
    {"split_index": 5,  "split_type": "run",     "station_key": "run_3",          "label": "Run 3 (1.2 km)",               "short_label": "R3"},
    {"split_index": 6,  "split_type": "station", "station_key": "sled_pull",      "label": "3. Sled Pull (50m)",           "short_label": "S3 Pull"},
    {"split_index": 7,  "split_type": "run",     "station_key": "run_4",          "label": "Run 4 (1.2 km)",               "short_label": "R4"},
    {"split_index": 8,  "split_type": "station", "station_key": "bbj",            "label": "4. Burpee Broad Jumps (80m)",  "short_label": "S4 BBJ"},
    {"split_index": 9,  "split_type": "run",     "station_key": "run_5",          "label": "Run 5 (1.2 km)",               "short_label": "R5"},
    {"split_index": 10, "split_type": "station", "station_key": "row",            "label": "5. Row (1,000m)",              "short_label": "S5 Row"},
    {"split_index": 11, "split_type": "run",     "station_key": "run_6",          "label": "Run 6 (1.2 km)",               "short_label": "R6"},
    {"split_index": 12, "split_type": "station", "station_key": "farmers_carry",  "label": "6. Farmers Carry (200m)",      "short_label": "S6 Carry"},
    {"split_index": 13, "split_type": "run",     "station_key": "run_7",          "label": "Run 7 (1.2 km)",               "short_label": "R7"},
    {"split_index": 14, "split_type": "station", "station_key": "sandbag_lunges", "label": "7. Sandbag Lunges (100m)",     "short_label": "S7 Lunges"},
    {"split_index": 15, "split_type": "run",     "station_key": "run_8",          "label": "Run 8 (1.2 km)",               "short_label": "R8"},
    {"split_index": 16, "split_type": "station", "station_key": "wall_balls",     "label": "8. Wall Balls",                "short_label": "S8 Wall Balls"},
]

AGE_CATEGORIES = [
    "U24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59", "60+"
]

# ── Built-in Official HYROX Weights & Reps Matrix per Division (9 Divisions) ─

HYROX_DIVISIONS = {
    "women_open": {
        "key": "women_open",
        "label": "Female Open",
        "short_label": "F Open",
        "color": "#38bdf8",
        "is_doubles": False,
        "weight_profile": "female_open",
        "weight_summary": "Push 102kg · Pull 78kg · Carry 2×16kg · Lunge 10kg · WB 4kg (75)",
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
    "women_doubles": {
        "key": "women_doubles",
        "label": "Female Doubles",
        "short_label": "F Doubles",
        "color": "#ec4899",
        "is_doubles": True,
        "weight_profile": "female_open",
        "weight_summary": "Push 102kg · Pull 78kg · Carry 2×16kg · Lunge 10kg · WB 4kg (100 split)",
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
    "women_pro": {
        "key": "women_pro",
        "label": "Female Pro",
        "short_label": "F Pro",
        "color": "#f43f5e",
        "is_doubles": False,
        "weight_profile": "female_pro",
        "weight_summary": "Push 152kg · Pull 103kg · Carry 2×24kg · Lunge 20kg · WB 6kg (100)",
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
    "women_pro_doubles": {
        "key": "women_pro_doubles",
        "label": "Female Pro Doubles",
        "short_label": "F Pro Dbl",
        "color": "#fb7185",
        "is_doubles": True,
        "weight_profile": "female_pro",
        "weight_summary": "Push 152kg · Pull 103kg · Carry 2×24kg · Lunge 20kg · WB 6kg (100 split)",
        "wall_ball_target_reps": 100,
        "stations": {
            "skierg":         {"distance": "1,000m (split)",  "weight": "Partners split work", "prescription": "SkiErg 1000m (split)"},
            "sled_push":      {"distance": "50m (split)",     "weight": "152 kg (incl. sled)", "prescription": "Sled Push 50m @ 152 kg"},
            "sled_pull":      {"distance": "50m (split)",     "weight": "103 kg (incl. sled)", "prescription": "Sled Pull 50m @ 103 kg"},
            "bbj":            {"distance": "80m (split)",     "weight": "Bodyweight (split)",  "prescription": "Burpee Broad Jump 80m (split)"},
            "row":            {"distance": "1,000m (split)",  "weight": "Partners split work", "prescription": "Row 1000m (split)"},
            "farmers_carry":  {"distance": "200m (split)",    "weight": "2×24 kg",             "prescription": "Farmers Carry 200m @ 2×24 kg"},
            "sandbag_lunges": {"distance": "100m (split)",    "weight": "20 kg",               "prescription": "Sandbag Lunges 100m @ 20 kg"},
            "wall_balls":     {"distance": "100 reps (split)","weight": "6 kg (2.7m target)",  "prescription": "Wall Balls 100 reps @ 6 kg (2.7m target)"},
        },
    },
    "men_open": {
        "key": "men_open",
        "label": "Men's Open",
        "short_label": "M Open",
        "color": "#3DFF4F",
        "is_doubles": False,
        "weight_profile": "men_open",
        "weight_summary": "Push 152kg · Pull 103kg · Carry 2×24kg · Lunge 20kg · WB 6kg (100)",
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
    "men_doubles": {
        "key": "men_doubles",
        "label": "Men's Open Doubles",
        "short_label": "M Open Dbl",
        "color": "#14b8a6",
        "is_doubles": True,
        "weight_profile": "men_open",
        "weight_summary": "Push 152kg · Pull 103kg · Carry 2×24kg · Lunge 20kg · WB 6kg (100 split)",
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
    "mixed_doubles": {
        "key": "mixed_doubles",
        "label": "Mixed Doubles",
        "short_label": "Mixed Dbl",
        "color": "#a855f7",
        "is_doubles": True,
        "weight_profile": "men_open",
        "weight_summary": "Push 152kg · Pull 103kg · Carry 2×24kg · Lunge 20kg · WB 6kg (100 split)",
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
    "men_pro": {
        "key": "men_pro",
        "label": "Men's Pro",
        "short_label": "M Pro",
        "color": "#f59e0b",
        "is_doubles": False,
        "weight_profile": "men_pro",
        "weight_summary": "Push 202kg · Pull 153kg · Carry 2×32kg · Lunge 30kg · WB 9kg (100)",
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
    "men_pro_doubles": {
        "key": "men_pro_doubles",
        "label": "Men's Pro Doubles",
        "short_label": "M Pro Dbl",
        "color": "#fbbf24",
        "is_doubles": True,
        "weight_profile": "men_pro",
        "weight_summary": "Push 202kg · Pull 153kg · Carry 2×32kg · Lunge 30kg · WB 9kg (100 split)",
        "wall_ball_target_reps": 100,
        "stations": {
            "skierg":         {"distance": "1,000m (split)",  "weight": "Partners split work", "prescription": "SkiErg 1000m (split)"},
            "sled_push":      {"distance": "50m (split)",     "weight": "202 kg (incl. sled)", "prescription": "Sled Push 50m @ 202 kg"},
            "sled_pull":      {"distance": "50m (split)",     "weight": "153 kg (incl. sled)", "prescription": "Sled Pull 50m @ 153 kg"},
            "bbj":            {"distance": "80m (split)",     "weight": "Bodyweight (split)",  "prescription": "Burpee Broad Jump 80m (split)"},
            "row":            {"distance": "1,000m (split)",  "weight": "Partners split work", "prescription": "Row 1000m (split)"},
            "farmers_carry":  {"distance": "200m (split)",    "weight": "2×32 kg",             "prescription": "Farmers Carry 200m @ 2×32 kg"},
            "sandbag_lunges": {"distance": "100m (split)",    "weight": "30 kg",               "prescription": "Sandbag Lunges 100m @ 30 kg"},
            "wall_balls":     {"distance": "100 reps (split)","weight": "9 kg (3.0m target)",  "prescription": "Wall Balls 100 reps @ 9 kg (3.0m target)"},
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


def calc_kph(duration_ms, distance_km=HYROX_RUN_DISTANCE_KM):
    """Calculate speed in km/h (KPH) given duration_ms and distance_km (default 1.2 km per run)."""
    if duration_ms is None:
        return None
    try:
        ms = int(duration_ms)
    except (TypeError, ValueError):
        return None
    if ms <= 0 or not distance_km or distance_km <= 0:
        return None
    hours = ms / 3_600_000.0
    return round(distance_km / hours, 1)


def format_kph(duration_ms, distance_km=HYROX_RUN_DISTANCE_KM):
    kph = calc_kph(duration_ms, distance_km)
    if kph is None:
        return "—"
    return f"{kph:.1f} kph"


def format_pace_per_km(duration_ms, distance_km=HYROX_RUN_DISTANCE_KM):
    if duration_ms is None or not distance_km or distance_km <= 0:
        return "—"
    try:
        ms = int(duration_ms)
    except (TypeError, ValueError):
        return "—"
    if ms <= 0:
        return "—"
    ms_per_km = int(round(ms / float(distance_km)))
    return f"{format_ms(ms_per_km)}/km"


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
    is_female = ("women" in s or "female" in s or "ladies" in s or s.startswith("w_") or s.startswith("f_"))
    is_male = ("men" in s or "male" in s or s.startswith("m_")) and not is_female
    is_double = ("double" in s or "pair" in s or "dbl" in s)
    is_pro = ("pro" in s)
    if "mixed" in s or ("mix" in s and is_double):
        return "mixed_doubles"
    if is_female and is_pro and is_double:
        return "women_pro_doubles"
    if is_male and is_pro and is_double:
        return "men_pro_doubles"
    if is_female and is_double:
        return "women_doubles"
    if is_male and is_double:
        return "men_doubles"
    if is_female and is_pro:
        return "women_pro"
    if is_female:
        return "women_open"
    if is_male and is_pro:
        return "men_pro"
    if is_double:
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
            "distance": "1.2 km (1,200m Extended Loop)",
            "distance_km": HYROX_RUN_DISTANCE_KM,
            "weight": "1.2 km Run",
            "prescription": f"{tmpl['label']} — Extended Run Loop (No Roxzone)",
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
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            name                    TEXT NOT NULL,
            event_date              TEXT NOT NULL,
            end_date                TEXT NOT NULL DEFAULT '',
            num_days                INTEGER NOT NULL DEFAULT 2,
            venue                   TEXT NOT NULL DEFAULT 'CS Performance Studio',
            wave_interval_mins      INTEGER NOT NULL DEFAULT 20,
            lanes_per_wave          INTEGER NOT NULL DEFAULT 1,
            transition_buffer_mins  INTEGER NOT NULL DEFAULT 10,
            status                  TEXT NOT NULL DEFAULT 'live',
            notes                   TEXT NOT NULL DEFAULT '',
            created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id                INTEGER NOT NULL REFERENCES hyrox_events(id) ON DELETE CASCADE,
            heat_number             INTEGER NOT NULL DEFAULT 1,
            day_number              INTEGER NOT NULL DEFAULT 1,
            slot_date               TEXT NOT NULL DEFAULT '',
            division_block          TEXT NOT NULL DEFAULT '',
            transition_buffer_mins  INTEGER NOT NULL DEFAULT 0,
            name                    TEXT NOT NULL,
            start_time              TEXT NOT NULL DEFAULT '08:00',
            max_lanes               INTEGER NOT NULL DEFAULT 1,
            status                  TEXT NOT NULL DEFAULT 'scheduled'
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

        CREATE TABLE IF NOT EXISTS hyrox_settings (
            key                 TEXT PRIMARY KEY,
            value               TEXT NOT NULL DEFAULT '',
            updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS hyrox_webhook_logs (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            webhook_id          TEXT NOT NULL,
            feed_item_id        TEXT NOT NULL DEFAULT '',
            feed_item_type      TEXT NOT NULL DEFAULT '',
            customer_id         TEXT NOT NULL DEFAULT '',
            teamup_event_id     TEXT NOT NULL DEFAULT '',
            status              TEXT NOT NULL DEFAULT 'processed',
            summary             TEXT NOT NULL DEFAULT '',
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    ev_cols = {r["name"] for r in db.execute("PRAGMA table_info(hyrox_events)").fetchall()}
    for col_name, col_def in [
        ("end_date", "TEXT NOT NULL DEFAULT ''"),
        ("num_days", "INTEGER NOT NULL DEFAULT 2"),
        ("transition_buffer_mins", "INTEGER NOT NULL DEFAULT 10"),
    ]:
        if col_name not in ev_cols:
            db.execute(f"ALTER TABLE hyrox_events ADD COLUMN {col_name} {col_def}")

    heat_cols = {r["name"] for r in db.execute("PRAGMA table_info(hyrox_heats)").fetchall()}
    for col_name, col_def in [
        ("day_number", "INTEGER NOT NULL DEFAULT 1"),
        ("slot_date", "TEXT NOT NULL DEFAULT ''"),
        ("division_block", "TEXT NOT NULL DEFAULT ''"),
        ("transition_buffer_mins", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        if col_name not in heat_cols:
            db.execute(f"ALTER TABLE hyrox_heats ADD COLUMN {col_name} {col_def}")

    count = db.execute("SELECT COUNT(*) as c FROM hyrox_events").fetchone()["c"]
    if count == 0:
        seed_default_hyrox_data(db)
        db.commit()
    else:
        # Upgrade legacy 4-lane-wave demo seed to the 2-day 1:1 division-block demo schedule
        legacy_demo = db.execute(
            "SELECT id, lanes_per_wave FROM hyrox_events WHERE name='CS Performance HYROX Sim — Nov 2026' LIMIT 1"
        ).fetchone()
        if legacy_demo and int(legacy_demo["lanes_per_wave"] or 1) > 1:
            db.execute("DELETE FROM hyrox_splits")
            db.execute("DELETE FROM hyrox_entries")
            db.execute("DELETE FROM hyrox_heats")
            db.execute("DELETE FROM hyrox_events")
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

    # 2. Featured Event: "CS Performance HYROX Sim — Nov 2026" (2-Day Weekend Sim, 1 Athlete/Pair + 1 Volunteer per Slot)
    cur_nov = db.execute(
        "INSERT INTO hyrox_events (name, event_date, end_date, num_days, venue, wave_interval_mins, lanes_per_wave, transition_buffer_mins, status, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "CS Performance HYROX Sim — Nov 2026",
            "2026-11-14",
            "2026-11-15",
            2,
            "CS Performance Studio",
            20,
            1,
            10,
            "live",
            "2-Day HYROX Sim Weekend (Sat & Sun). 1 Athlete/Pair + 1 Volunteer per Slot with Weight-Change Buffers between Division Blocks.",
        ),
    )
    nov_event_id = cur_nov.lastrowid

    # 1:1 Solo/Pair Time Slots across Day 1 (Sat) & Day 2 (Sun) grouped by Division Blocks
    heats_spec = [
        (1, 1, "2026-11-14", "men_open",       0,  "Day 1 · 08:00 — Men's Open",        "08:00", 1, "completed"),
        (2, 1, "2026-11-14", "men_open",       10, "Day 1 · 08:20 — Men's Open",        "08:20", 1, "completed"),
        (3, 1, "2026-11-14", "women_open",     10, "Day 1 · 08:50 — Female Open",       "08:50", 1, "completed"),
        (4, 1, "2026-11-14", "women_pro",      10, "Day 1 · 09:20 — Female Pro",        "09:20", 1, "completed"),
        (5, 1, "2026-11-14", "mixed_doubles",  10, "Day 1 · 09:50 — Mixed Doubles",     "09:50", 1, "completed"),
        (6, 1, "2026-11-14", "men_pro",        10, "Day 1 · 10:20 — Men's Pro",         "10:20", 1, "racing"),
        (7, 2, "2026-11-15", "women_doubles",  10, "Day 2 · 08:00 — Female Doubles",    "08:00", 1, "racing"),
        (8, 2, "2026-11-15", "men_open",       10, "Day 2 · 08:30 — Men's Open",        "08:30", 1, "scheduled"),
        (9, 2, "2026-11-15", "women_open",     10, "Day 2 · 09:00 — Female Open",       "09:00", 1, "scheduled"),
        (10, 2, "2026-11-15", "men_doubles",   10, "Day 2 · 09:30 — Men's Open Doubles","09:30", 1, "scheduled"),
    ]
    heat_ids = {}
    for h_num, day_num, s_date, div_blk, buf_m, h_name, h_time, h_lanes, h_status in heats_spec:
        c = db.execute(
            "INSERT INTO hyrox_heats (event_id, heat_number, day_number, slot_date, division_block, transition_buffer_mins, name, start_time, max_lanes, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (nov_event_id, h_num, day_num, s_date, div_blk, buf_m, h_name, h_time, h_lanes, h_status),
        )
        heat_ids[h_num] = c.lastrowid

    # Day 1 Finished Entries (1 Athlete/Pair + 1 Volunteer per slot):
    # Slot 1 (08:00): Ewan Taylor (Men's Open) — Improved to 1:09:42 (4182s — 4m33s PB over Sep!)
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

    # Slot 2 (08:20): Alan Mackay (Men's Open) — 1:12:08
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
        nov_event_id, heat_ids[2], alan_id, None, "Alan Mackay", "",
        "alan.mackay@example.com", "102", "men_open", "40-44", "Coach Laura", "1102",
        alan_nov_splits, wall_balls=100, start_offset_ms=5400000
    )

    # Slot 3 (08:50): Sarah Jenkins (Female Open) — 1:14:36
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
        nov_event_id, heat_ids[3], sarah_id, None, "Sarah Jenkins", "",
        "sarah.jenkins@example.com", "103", "women_open", "30-34", "Sam Walker", "1103",
        sarah_nov_splits, wall_balls=75, start_offset_ms=5400000
    )

    # Slot 4 (09:20): Laura Mitchell (Female Pro) — 1:08:25
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
        nov_event_id, heat_ids[4], laura_id, None, "Laura Mitchell", "",
        "laura.mitchell@example.com", "104", "women_pro", "30-34", "Jamie Ross", "1104",
        laura_nov_splits, wall_balls=100, start_offset_ms=5400000
    )

    # Slot 5 (09:50): Chris Smith & Emma Wallace (Mixed Doubles) — 1:03:50
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
        nov_event_id, heat_ids[5], chris_id, emma_id, "Chris Smith", "Emma Wallace",
        "chris.smith@example.com", "201", "mixed_doubles", "35-39", "Katie Bell", "1201",
        mixed_nov_splits, wall_balls=100, start_offset_ms=4200000
    )

    # Racing Entries (Live on the gym floor right now!):
    callum_partial = [255, 232, 264, 192, 270, 228, 276, 248, 274, 240, 268]
    callum_elapsed_ms = sum(s * 1000 for s in callum_partial)
    callum_start_ms = now_ms - callum_elapsed_ms - 65000
    cur_cal = db.execute(
        "INSERT INTO hyrox_entries (event_id, heat_id, athlete_id, display_name, email, bib_number, "
        "division, age_category, volunteer_name, judge_pin, status, started_at_ms, wall_ball_reps) "
        "VALUES (?, ?, ?, 'Callum Fraser', 'callum.fraser@example.com', '105', 'men_pro', '25-29', 'Alex Reid', '1105', 'racing', ?, 0)",
        (nov_event_id, heat_ids[6], callum_id, callum_start_ms)
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
        (nov_event_id, heat_ids[7], kirsty_id, megan_id, km_start_ms)
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

    # Day 2 Scheduled Entries (On Deck — 1 Racer/Pair + 1 Volunteer per slot):
    scheduled_specs = [
        (heat_ids[8],  ross_id,   None,    "Ross MacLeod", "",             "ross.macleod@example.com", "106", "men_open",    "30-34", "Coach Chris", "1106"),
        (heat_ids[9],  hannah_id, None,    "Hannah Reid",  "",             "hannah.reid@example.com",  "107", "women_open",  "25-29", "Coach Laura", "1107"),
        (heat_ids[10], dave_id,   mark_id, "Dave Kerr",    "Mark Stewart", "dave.kerr@example.com",    "203", "men_doubles", "35-39", "Coach Chris", "1203"),
    ]
    for h_id, a_id, p_id, d_name, p_name, em, bib, div, age_c, vol, pin in scheduled_specs:
        c = db.execute(
            "INSERT INTO hyrox_entries (event_id, heat_id, athlete_id, partner_athlete_id, display_name, partner_name, "
            "email, bib_number, division, age_category, volunteer_name, judge_pin, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled')",
            (nov_event_id, h_id, a_id, p_id, d_name, p_name, em, bib, div, age_c, vol, pin)
        )
        ensure_entry_splits(db, c.lastrowid)


ROXFIT_SPLIT_LABELS = {
    1: "Run 1",
    2: "Ski",
    3: "Run 2",
    4: "Sled Push",
    5: "Run 3",
    6: "Sled Pull",
    7: "Run 4",
    8: "Burpee Broad Jump",
    9: "Run 5",
    10: "Row",
    11: "Run 6",
    12: "Farmers Carry",
    13: "Run 7",
    14: "Sandbag Lunge",
    15: "Run 8",
    16: "Wall Balls",
}


# ── Serialization Helpers ───────────────────────────────────────────────────

def serialize_entry(db, entry_row, include_splits=True, include_history=False):
    e = dict(entry_row)
    div_key = e.get("division") or "men_open"
    div_info = HYROX_DIVISIONS.get(div_key, HYROX_DIVISIONS["men_open"])
    e["division_label"] = div_info["label"]
    e["division_short_label"] = div_info["short_label"]
    e["division_color"] = div_info["color"]
    e["is_doubles"] = div_info["is_doubles"]
    e["weight_profile"] = div_info.get("weight_profile", "men_open")
    e["weight_summary"] = div_info.get("weight_summary", "")
    e["wall_ball_target_reps"] = div_info["wall_ball_target_reps"]
    e["full_display_name"] = (
        f"{e['display_name']} & {e['partner_name']}"
        if e.get("partner_name")
        else e["display_name"]
    )

    heat = None
    if e.get("heat_id"):
        heat = db.execute("SELECT * FROM hyrox_heats WHERE id=?", (e["heat_id"],)).fetchone()
    heat_dict = dict(heat) if heat else {}
    e["heat_name"] = heat_dict.get("name") or "Unassigned"
    e["heat_start_time"] = heat_dict.get("start_time") or "—"
    e["heat_number"] = heat_dict.get("heat_number") or 0
    e["heat_day_number"] = int(heat_dict.get("day_number") or 1)
    e["heat_slot_date"] = heat_dict.get("slot_date") or ""
    e["heat_division_block"] = heat_dict.get("division_block") or ""

    e["total_formatted"] = format_ms(e.get("total_ms"), include_hours=True)
    e["run_total_formatted"] = format_ms(e.get("run_total_ms"))
    e["station_total_formatted"] = format_ms(e.get("station_total_ms"))
    e["penalty_formatted"] = format_ms(e.get("penalty_ms")) if e.get("penalty_ms") else "00:00"
    e["run_distance_km"] = HYROX_RUN_DISTANCE_KM
    e["total_run_distance_km"] = round(HYROX_RUN_DISTANCE_KM * 8, 1)

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
            sd["label"] = HYROX_SPLITS_TEMPLATE[idx - 1]["label"]
            sd["short_label"] = HYROX_SPLITS_TEMPLATE[idx - 1]["short_label"]
            sd["roxfit_label"] = ROXFIT_SPLIT_LABELS.get(idx, sd["label"])
            sd["prescription"] = presc["prescription"]
            sd["distance"] = presc["distance"]
            sd["weight"] = presc["weight"]
            sd["duration_formatted"] = format_ms(sd.get("duration_ms"))
            sd["is_pb"] = False
            sd["split_rank"] = None
            sd["division_split_rank"] = None
            if sd["split_type"] == "run":
                sd["distance_km"] = HYROX_RUN_DISTANCE_KM
                sd["pace_kph"] = calc_kph(sd.get("duration_ms"), HYROX_RUN_DISTANCE_KM)
                sd["pace_kph_formatted"] = format_kph(sd.get("duration_ms"), HYROX_RUN_DISTANCE_KM)
                sd["pace_per_km_formatted"] = format_pace_per_km(sd.get("duration_ms"), HYROX_RUN_DISTANCE_KM)
            else:
                sd["distance_km"] = None
                sd["pace_kph"] = None
                sd["pace_kph_formatted"] = None
                sd["pace_per_km_formatted"] = None
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
        e["avg_run_kph"] = calc_kph(e["avg_run_ms"], HYROX_RUN_DISTANCE_KM)
        e["avg_run_kph_formatted"] = format_kph(e["avg_run_ms"], HYROX_RUN_DISTANCE_KM)
        e["avg_run_pace_per_km_formatted"] = format_pace_per_km(e["avg_run_ms"], HYROX_RUN_DISTANCE_KM)
        e["avg_run_rank"] = None
        e["avg_station_ms"] = int(sum(station_durations) / len(station_durations)) if station_durations else None
        e["avg_station_formatted"] = format_ms(e["avg_station_ms"])
        max_split_ms = max([s["duration_ms"] for s in splits if s.get("duration_ms") is not None] or [360000])
        e["max_split_ms"] = max(max_split_ms, 180000)
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
            "avg_run_kph": calc_kph(r["run_total_ms"], HYROX_RUN_DISTANCE_KM * 8),
            "avg_run_kph_formatted": format_kph(r["run_total_ms"], HYROX_RUN_DISTANCE_KM * 8),
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
            cur_kph = calc_kph(cur_dur, HYROX_RUN_DISTANCE_KM) if sp["split_type"] == "run" else None
            prev_kph = calc_kph(prev_dur, HYROX_RUN_DISTANCE_KM) if sp["split_type"] == "run" else None
            kph_delta = round(cur_kph - prev_kph, 1) if (cur_kph is not None and prev_kph is not None) else None
            prior_durs = [
                s["split_map"].get(idx)
                for s in sims
                if s["entry_id"] != cur_id and s["split_map"].get(idx) is not None
            ]
            is_pb = bool(cur_dur is not None and prior_durs and cur_dur <= min(prior_durs))
            sp["is_pb"] = is_pb
            split_deltas.append({
                "split_index": idx,
                "label": sp["label"],
                "short_label": sp["short_label"],
                "roxfit_label": sp.get("roxfit_label", sp["label"]),
                "split_type": sp["split_type"],
                "current_ms": cur_dur,
                "current_formatted": format_ms(cur_dur),
                "previous_ms": prev_dur,
                "previous_formatted": format_ms(prev_dur),
                "delta_ms": delta,
                "delta_formatted": format_delta_ms(delta),
                "current_kph": cur_kph,
                "previous_kph": prev_kph,
                "kph_delta": kph_delta,
                "improved": (delta < 0) if delta is not None else None,
                "is_pb": is_pb,
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
    elif current_entry_dict.get("splits"):
        # For first-time sims, mark fastest run and fastest station as PB badges
        completed_runs = [s for s in current_entry_dict["splits"] if s["split_type"] == "run" and s.get("duration_ms") is not None]
        completed_stations = [s for s in current_entry_dict["splits"] if s["split_type"] == "station" and s.get("duration_ms") is not None]
        if completed_runs:
            best_run_ms = min(s["duration_ms"] for s in completed_runs)
            for s in completed_runs:
                if s["duration_ms"] == best_run_ms:
                    s["is_pb"] = True
                    break
        if completed_stations:
            best_st_ms = min(s["duration_ms"] for s in completed_stations)
            for s in completed_stations:
                if s["duration_ms"] == best_st_ms:
                    s["is_pb"] = True
                    break

    return {
        "sim_count": len(sims),
        "sims": sims,
        "comparison": comparison,
    }


def _compute_event_split_ranks(entries):
    """Assign avg_run_rank, split_rank, and division_split_rank across entries in an event."""
    with_avg_run = [e for e in entries if e.get("avg_run_ms") is not None]
    with_avg_run.sort(key=lambda x: x["avg_run_ms"])
    for r_idx, e in enumerate(with_avg_run, start=1):
        e["avg_run_rank"] = r_idx

    for split_idx in range(1, 17):
        pairs = []
        for e in entries:
            splits = e.get("splits") or []
            if len(splits) >= split_idx:
                sp = splits[split_idx - 1]
                if sp.get("duration_ms") is not None:
                    pairs.append((sp["duration_ms"], e["division"], sp))
        pairs.sort(key=lambda x: x[0])
        div_counters = {}
        for overall_rank, (_, div_k, sp_obj) in enumerate(pairs, start=1):
            sp_obj["split_rank"] = overall_rank
            div_counters[div_k] = div_counters.get(div_k, 0) + 1
            sp_obj["division_split_rank"] = div_counters[div_k]


def _annotate_weight_changeovers(heats, entries):
    """Detect division / weight-profile transitions between consecutive slots on the same day."""
    prev_day = None
    prev_div_key = None
    heat_by_id = {h["id"]: h for h in heats}
    for h in heats:
        h_entries = [e for e in entries if e.get("heat_id") == h["id"]]
        slot_div = h.get("division_block") or (h_entries[0]["division"] if h_entries else "")
        h["effective_division"] = slot_div
        div_meta = HYROX_DIVISIONS.get(slot_div)
        h["effective_division_label"] = div_meta["label"] if div_meta else ""
        h["weight_summary"] = div_meta.get("weight_summary", "") if div_meta else ""
        h["weight_change_from_prev"] = False
        h["weight_change_alert"] = ""
        day_num = int(h.get("day_number") or 1)
        if prev_day == day_num and prev_div_key and slot_div and slot_div != prev_div_key:
            prev_meta = HYROX_DIVISIONS.get(prev_div_key, {})
            cur_meta = HYROX_DIVISIONS.get(slot_div, {})
            if prev_meta.get("weight_profile") != cur_meta.get("weight_profile") or prev_div_key != slot_div:
                h["weight_change_from_prev"] = True
                h["weight_change_alert"] = (
                    f"⚖️ Equipment Changeover: {prev_meta.get('label', prev_div_key)} → "
                    f"{cur_meta.get('label', slot_div)} ({cur_meta.get('weight_summary', '')})"
                )
        if slot_div:
            prev_div_key = slot_div
        prev_day = day_num

    for e in entries:
        h = heat_by_id.get(e.get("heat_id"))
        e["weight_change_from_prev"] = bool(h.get("weight_change_from_prev")) if h else False
        e["weight_change_alert"] = (h.get("weight_change_alert") or "") if h else ""


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
        division_order=list(HYROX_DIVISIONS.keys()),
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
    all_rows = db.execute("SELECT * FROM hyrox_entries WHERE event_id=? ORDER BY id ASC", (row["event_id"],)).fetchall()
    all_entries = [serialize_entry(db, r, include_splits=True, include_history=(r["id"] == entry_id)) for r in all_rows]
    _compute_event_split_ranks(all_entries)
    entry_data = next((e for e in all_entries if e["id"] == entry_id), None) or serialize_entry(db, row, include_splits=True, include_history=True)
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
    all_rows = db.execute("SELECT * FROM hyrox_entries WHERE event_id=? ORDER BY id ASC", (latest_entry["event_id"],)).fetchall()
    all_entries = [serialize_entry(db, r, include_splits=True, include_history=(r["id"] == latest_entry["id"])) for r in all_rows]
    _compute_event_split_ranks(all_entries)
    entry_data = next((e for e in all_entries if e["id"] == latest_entry["id"]), None) or serialize_entry(db, latest_entry, include_splits=True, include_history=True)
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
    num_days = int(data.get("num_days") or 2)
    end_date = (data.get("end_date") or "").strip()
    if not end_date and num_days >= 2:
        try:
            d0 = datetime.strptime(event_date[:10], "%Y-%m-%d").date()
            from datetime import timedelta
            end_date = (d0 + timedelta(days=num_days - 1)).strftime("%Y-%m-%d")
        except Exception:
            end_date = event_date
    elif not end_date:
        end_date = event_date

    venue = (data.get("venue") or "CS Performance Studio").strip()
    wave_interval_mins = int(data.get("wave_interval_mins") or 20)
    lanes_per_wave = int(data.get("lanes_per_wave") or 1)
    transition_buffer_mins = int(data.get("transition_buffer_mins") if data.get("transition_buffer_mins") is not None else 10)
    status = (data.get("status") or "live").strip()
    notes = (data.get("notes") or "").strip()

    cur = db.execute(
        "INSERT INTO hyrox_events (name, event_date, end_date, num_days, venue, wave_interval_mins, lanes_per_wave, transition_buffer_mins, status, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, event_date, end_date, num_days, venue, wave_interval_mins, lanes_per_wave, transition_buffer_mins, status, notes)
    )
    event_id = cur.lastrowid

    num_waves = int(data.get("num_waves") if data.get("num_waves") is not None else 4)
    first_wave_time = (data.get("first_wave_time") or "08:00").strip()
    division_block = normalize_division(data["division_block"]) if data.get("division_block") else ""
    if num_waves > 0:
        _generate_heats_for_event(
            db, event_id, first_wave_time, num_waves, wave_interval_mins, lanes_per_wave,
            day_number=1, slot_date=event_date, division_block=division_block,
            transition_buffer_mins=transition_buffer_mins,
        )

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
    ev_d = dict(ev)
    data = request.get_json(force=True) or {}
    db.execute(
        "UPDATE hyrox_events SET name=?, event_date=?, end_date=?, num_days=?, venue=?, wave_interval_mins=?, lanes_per_wave=?, transition_buffer_mins=?, status=?, notes=? WHERE id=?",
        (
            data.get("name", ev_d["name"]),
            data.get("event_date", ev_d["event_date"]),
            data.get("end_date", ev_d.get("end_date", "")),
            int(data.get("num_days", ev_d.get("num_days") or 2)),
            data.get("venue", ev_d["venue"]),
            int(data.get("wave_interval_mins", ev_d["wave_interval_mins"])),
            int(data.get("lanes_per_wave", ev_d["lanes_per_wave"])),
            int(data.get("transition_buffer_mins", ev_d.get("transition_buffer_mins") or 10)),
            data.get("status", ev_d["status"]),
            data.get("notes", ev_d["notes"]),
            event_id,
        ),
    )
    db.commit()
    updated = db.execute("SELECT * FROM hyrox_events WHERE id=?", (event_id,)).fetchone()
    return jsonify(dict(updated))


def _generate_heats_for_event(
    db, event_id, start_time_str, count, interval_mins, max_lanes=1,
    day_number=1, slot_date="", division_block="", transition_buffer_mins=0
):
    try:
        parts = [int(p) for p in start_time_str.split(":")]
        start_total_mins = parts[0] * 60 + parts[1]
    except Exception:
        start_total_mins = 8 * 60

    existing_max = db.execute(
        "SELECT COALESCE(MAX(heat_number), 0) as m FROM hyrox_heats WHERE event_id=?",
        (event_id,)
    ).fetchone()["m"]

    div_label = HYROX_DIVISIONS.get(division_block, {}).get("label", "") if division_block else ""
    created = []
    for i in range(count):
        heat_num = existing_max + i + 1
        t_mins = start_total_mins + i * interval_mins
        hh = (t_mins // 60) % 24
        mm = t_mins % 60
        t_str = f"{hh:02d}:{mm:02d}"
        if div_label:
            h_name = f"Day {day_number} · {t_str} — {div_label}"
        else:
            h_name = f"Day {day_number} · Slot {heat_num} — {t_str}"
        buf_after = transition_buffer_mins if (i == count - 1) else 0
        cur = db.execute(
            "INSERT INTO hyrox_heats (event_id, heat_number, day_number, slot_date, division_block, transition_buffer_mins, name, start_time, max_lanes, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled')",
            (event_id, heat_num, int(day_number or 1), slot_date or "", division_block or "", int(buf_after or 0), h_name, t_str, int(max_lanes or 1))
        )
        created.append(cur.lastrowid)
    return created


@hyrox_bp.route("/api/hyrox/events/<int:event_id>/heats", methods=["POST"])
def api_create_or_generate_heats(event_id):
    db = get_db()
    ensure_hyrox_tables(db)
    ev = db.execute("SELECT * FROM hyrox_events WHERE id=?", (event_id,)).fetchone()
    ev_d = dict(ev) if ev else {}
    data = request.get_json(force=True) or {}
    day_number = int(data.get("day_number") or 1)
    slot_date = (data.get("slot_date") or (ev_d.get("end_date") if day_number == 2 else ev_d.get("event_date")) or "").strip()
    raw_div_block = (data.get("division_block") or "").strip()
    division_block = normalize_division(raw_div_block) if raw_div_block else ""
    transition_buffer_mins = int(data.get("transition_buffer_mins") if data.get("transition_buffer_mins") is not None else (ev_d.get("transition_buffer_mins") or 10))

    if data.get("generate_batch"):
        start_time = (data.get("start_time") or "08:00").strip()
        count = int(data.get("count") or 4)
        interval_mins = int(data.get("interval_mins") or ev_d.get("wave_interval_mins") or 20)
        max_lanes = int(data.get("max_lanes") or 1)
        _generate_heats_for_event(
            db, event_id, start_time, count, interval_mins, max_lanes,
            day_number=day_number, slot_date=slot_date, division_block=division_block,
            transition_buffer_mins=transition_buffer_mins,
        )
        db.commit()
    else:
        existing_max = db.execute(
            "SELECT COALESCE(MAX(heat_number), 0) as m FROM hyrox_heats WHERE event_id=?",
            (event_id,)
        ).fetchone()["m"]
        heat_num = int(data.get("heat_number") or (existing_max + 1))
        start_time = (data.get("start_time") or "08:00").strip()
        div_label = HYROX_DIVISIONS.get(division_block, {}).get("label", "") if division_block else ""
        default_name = f"Day {day_number} · {start_time} — {div_label}" if div_label else f"Day {day_number} · Slot {heat_num} — {start_time}"
        name = (data.get("name") or default_name).strip()
        max_lanes = int(data.get("max_lanes") or 1)
        db.execute(
            "INSERT INTO hyrox_heats (event_id, heat_number, day_number, slot_date, division_block, transition_buffer_mins, name, start_time, max_lanes, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, heat_num, day_number, slot_date, division_block, transition_buffer_mins, name, start_time, max_lanes, data.get("status", "scheduled"))
        )
        db.commit()

    heats = db.execute(
        "SELECT * FROM hyrox_heats WHERE event_id=? ORDER BY day_number ASC, start_time ASC, heat_number ASC",
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
    h_d = dict(heat)
    data = request.get_json(force=True) or {}
    db.execute(
        "UPDATE hyrox_heats SET heat_number=?, day_number=?, slot_date=?, division_block=?, transition_buffer_mins=?, name=?, start_time=?, max_lanes=?, status=? WHERE id=?",
        (
            int(data.get("heat_number", h_d["heat_number"])),
            int(data.get("day_number", h_d.get("day_number") or 1)),
            data.get("slot_date", h_d.get("slot_date") or ""),
            data.get("division_block", h_d.get("division_block") or ""),
            int(data.get("transition_buffer_mins", h_d.get("transition_buffer_mins") or 0)),
            data.get("name", h_d["name"]),
            data.get("start_time", h_d["start_time"]),
            int(data.get("max_lanes", h_d.get("max_lanes") or 1)),
            data.get("status", h_d["status"]),
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
            "SELECT * FROM hyrox_heats WHERE event_id=? ORDER BY day_number ASC, start_time ASC, heat_number ASC",
            (event_id,)
        ).fetchall()
    ]
    entry_rows = db.execute(
        "SELECT * FROM hyrox_entries WHERE event_id=? ORDER BY id ASC",
        (event_id,)
    ).fetchall()
    entries = [serialize_entry(db, r, include_splits=True, include_history=True) for r in entry_rows]

    entries.sort(key=lambda x: (int(x.get("heat_day_number") or 1), x.get("heat_start_time") or "99:99", x.get("bib_number") or "999", x["id"]))
    _compute_event_split_ranks(entries)
    _annotate_weight_changeovers(heats, entries)

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

def _normalize_heat_time_str(raw_time):
    """Normalize ISO-8601 timestamps ('2026-11-14T08:15:00Z'), '8:15 AM', or '08:15:00' to 'HH:MM'."""
    if not raw_time:
        return ""
    s = str(raw_time).strip()
    m_iso = re.search(r"T(\d{2}):(\d{2})", s)
    if m_iso:
        return f"{int(m_iso.group(1)):02d}:{int(m_iso.group(2)):02d}"
    m_ampm = re.search(r"\b(\d{1,2}):(\d{2})\s*(AM|PM)\b", s, re.IGNORECASE)
    if m_ampm:
        hh = int(m_ampm.group(1))
        mm = int(m_ampm.group(2))
        mer = m_ampm.group(3).upper()
        if mer == "PM" and hh < 12:
            hh += 12
        elif mer == "AM" and hh == 12:
            hh = 0
        return f"{hh:02d}:{mm:02d}"
    m_hhmm = re.search(r"\b(\d{1,2}):(\d{2})\b", s)
    if m_hhmm:
        hh = int(m_hhmm.group(1))
        mm = int(m_hhmm.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return f"{hh:02d}:{mm:02d}"
    return s


def _create_entry_record(db, event_id, payload, upsert=False):
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
    heat_time = _normalize_heat_time_str(payload.get("heat_time") or payload.get("wave_time") or "")
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

    if upsert:
        existing_entry = None
        if athlete_id:
            existing_entry = db.execute(
                "SELECT * FROM hyrox_entries WHERE event_id=? AND athlete_id=? LIMIT 1",
                (event_id, athlete_id)
            ).fetchone()
        if not existing_entry and email:
            existing_entry = db.execute(
                "SELECT * FROM hyrox_entries WHERE event_id=? AND LOWER(email)=? LIMIT 1",
                (event_id, email)
            ).fetchone()
        if not existing_entry:
            existing_entry = db.execute(
                "SELECT * FROM hyrox_entries WHERE event_id=? AND LOWER(display_name)=? LIMIT 1",
                (event_id, display_name.lower())
            ).fetchone()
        if existing_entry:
            has_exp_div = payload.get("has_explicit_division", bool(payload.get("division")))
            has_exp_age = payload.get("has_explicit_age", bool(payload.get("age_category") or dob))
            new_heat_id = existing_entry["heat_id"] if existing_entry["heat_id"] is not None else heat_id
            if payload.get("force_heat_time") and heat_id is not None:
                new_heat_id = heat_id
            new_partner = partner_name or existing_entry["partner_name"]
            new_partner_aid = partner_athlete_id or existing_entry["partner_athlete_id"]
            if existing_entry["partner_name"] and not partner_name:
                new_div = existing_entry["division"]
            else:
                new_div = division if has_exp_div else existing_entry["division"]
            new_age = age_cat if has_exp_age else existing_entry["age_category"]
            new_vol = existing_entry["volunteer_name"] or volunteer_name
            new_notes = existing_entry["notes"] or notes
            db.execute(
                "UPDATE hyrox_entries SET heat_id=?, athlete_id=?, partner_athlete_id=?, display_name=?, "
                "partner_name=?, email=?, division=?, age_category=?, volunteer_name=?, notes=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (
                    new_heat_id,
                    athlete_id,
                    new_partner_aid,
                    display_name,
                    new_partner,
                    email or existing_entry["email"],
                    new_div,
                    new_age,
                    new_vol,
                    new_notes,
                    existing_entry["id"],
                ),
            )
            ensure_entry_splits(db, existing_entry["id"])
            return existing_entry["id"], None

    bib_number = str(payload.get("bib_number") or payload.get("bib") or "").strip()
    if not bib_number:
        cnt = db.execute("SELECT COUNT(*) as c FROM hyrox_entries WHERE event_id=?", (event_id,)).fetchone()["c"]
        bib_number = str(101 + cnt)

    judge_pin = _generate_unique_pin(db, event_id, str(payload.get("judge_pin") or "").strip() or None)

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

    full_name = _pick("display_name", ["name", "full_name", "athlete", "athlete_name", "client_name", "customer_name", "member_name", "display_name", "customer"])
    first_name = _pick("first_name", ["first_name", "firstname", "given_name", "first", "customer_first_name"])
    last_name = _pick("last_name", ["last_name", "lastname", "surname", "family_name", "last", "customer_last_name"])
    if not full_name and (first_name or last_name):
        full_name = f"{first_name} {last_name}".strip()

    return {
        "display_name": full_name,
        "email": _pick("email", ["email", "email_address", "customer_email", "e_mail"]),
        "dob": _pick("dob", ["dob", "date_of_birth", "birth_date", "birthdate", "birthday"]),
        "age_category": _pick("age_category", ["age_category", "age_group", "age", "age_cat", "category_age"]),
        "division": _pick("division", [
            "division", "category", "race_division", "hyrox_division", "ticket_type",
            "class_type", "membership", "offering", "offering_type", "offering_name",
            "event_name", "class_name", "customer_membership",
        ]),
        "partner_name": _pick("partner_name", ["partner_name", "partner", "doubles_partner", "teammate", "athlete_2"]),
        "heat_time": _normalize_heat_time_str(_pick("heat_time", [
            "heat_time", "wave_time", "start_time", "heat", "wave", "time_slot",
            "session_time", "event_time", "starts", "starts_at", "local_starts_at", "time",
        ])),
        "bib_number": _pick("bib_number", ["bib", "bib_number", "race_number", "number"]),
        "volunteer_name": _pick("volunteer_name", ["volunteer", "volunteer_name", "judge", "judge_name", "lane_judge", "instructor"]),
        "teamup_customer_id": _pick("teamup_customer_id", ["customer_id", "teamup_id", "teamup_customer_id", "member_id", "id"]),
        "notes": _pick("notes", ["notes", "booking_notes", "attendance_notes", "comment", "comments"]),
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
    new_division = normalize_division(data.get("division", row["division"]))
    new_age_cat = normalize_age_category(data.get("age_category", row["age_category"]))
    new_display_name = (data.get("display_name", row["display_name"]) or "").strip() or row["display_name"]
    new_partner_name = (data.get("partner_name", row["partner_name"]) or "").strip()
    new_email = (data.get("email", row["email"]) or "").strip().lower()
    new_bib = str(data.get("bib_number", row["bib_number"]) or "").strip() or row["bib_number"]
    new_volunteer = (data.get("volunteer_name", row["volunteer_name"]) or "").strip()
    new_pin = str(data.get("judge_pin", row["judge_pin"]) or "").strip()
    new_status = (data.get("status", row["status"]) or "scheduled").strip()
    new_notes = (data.get("notes", row["notes"]) or "").strip()
    new_wb_reps = int(data.get("wall_ball_reps", row["wall_ball_reps"] or 0) or 0)

    # Support creating/assigning a custom 1:1 time slot on the fly if custom_slot_time is provided
    custom_slot_time = _normalize_heat_time_str(data.get("custom_slot_time") or data.get("heat_time") or "")
    custom_slot_day = int(data.get("custom_slot_day") or 1)
    if custom_slot_time and re.match(r"^\d{2}:\d{2}$", custom_slot_time):
        existing_heat = db.execute(
            "SELECT id FROM hyrox_heats WHERE event_id=? AND day_number=? AND start_time=? LIMIT 1",
            (row["event_id"], custom_slot_day, custom_slot_time)
        ).fetchone()
        if existing_heat:
            new_heat_id = existing_heat["id"]
        else:
            ev_row = db.execute("SELECT * FROM hyrox_events WHERE id=?", (row["event_id"],)).fetchone()
            ev_d = dict(ev_row) if ev_row else {}
            slot_date = (ev_d.get("end_date") if custom_slot_day == 2 else ev_d.get("event_date")) or ""
            max_h = db.execute(
                "SELECT COALESCE(MAX(heat_number), 0) as m FROM hyrox_heats WHERE event_id=?",
                (row["event_id"],)
            ).fetchone()["m"]
            h_num = max_h + 1
            div_label = HYROX_DIVISIONS.get(new_division, {}).get("label", "")
            h_name = f"Day {custom_slot_day} · {custom_slot_time} — {div_label}" if div_label else f"Day {custom_slot_day} · Slot {h_num} — {custom_slot_time}"
            cur_h = db.execute(
                "INSERT INTO hyrox_heats (event_id, heat_number, day_number, slot_date, division_block, transition_buffer_mins, name, start_time, max_lanes, status) "
                "VALUES (?, ?, ?, ?, ?, 0, ?, ?, 1, 'scheduled')",
                (row["event_id"], h_num, custom_slot_day, slot_date, new_division, h_name, custom_slot_time)
            )
            new_heat_id = cur_h.lastrowid
    else:
        new_heat_id = data.get("heat_id", row["heat_id"])
        if new_heat_id == "" or new_heat_id == 0:
            new_heat_id = None
        elif new_heat_id is not None:
            new_heat_id = int(new_heat_id)

    new_athlete_id = find_or_create_athlete(
        db,
        full_name=new_display_name,
        email=new_email,
        age_category=new_age_cat,
    ) or row["athlete_id"]
    new_partner_athlete_id = (
        find_or_create_athlete(db, full_name=new_partner_name, age_category=new_age_cat)
        if new_partner_name
        else None
    )

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
        "UPDATE hyrox_entries SET heat_id=?, athlete_id=?, partner_athlete_id=?, display_name=?, partner_name=?, "
        "email=?, bib_number=?, division=?, age_category=?, volunteer_name=?, judge_pin=?, status=?, "
        "penalty_ms=?, wall_ball_reps=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (
            new_heat_id,
            new_athlete_id,
            new_partner_athlete_id,
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
            new_wb_reps,
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


# ── TeamUp REST API v2 Client & Live Sync / Webhook Integration ─────────────
# Official Spec: https://docs.goteamup.com & https://goteamup.com/api/v2/schema/?format=json
# Base URL:      https://goteamup.com/api/v2  (Note: api.goteamup.com does NOT exist)
# Auth Header:   Authorization: Bearer <M2M_OR_OAUTH_TOKEN>
# Mode Header:   TeamUp-Request-Mode: provider
# Provider Hdr:  TeamUp-Provider-ID: <NUMERIC_BUSINESS_ID>

TEAMUP_DEFAULT_BASE_URL = "https://goteamup.com/api/v2"
TEAMUP_DEFAULT_PROVIDER_ID = "13050192"


def get_teamup_config(db):
    """Retrieve TeamUp API v2 configuration from hyrox_settings with env var fallbacks."""
    ensure_hyrox_tables(db)
    rows = db.execute("SELECT key, value FROM hyrox_settings").fetchall()
    stored = {r["key"]: r["value"] for r in rows}

    raw_token = (stored.get("teamup_api_token") or os.environ.get("TEAMUP_API_TOKEN") or "").strip()
    # Strip any accidental prefix so we always format exact 'Bearer <token>'
    clean_token = re.sub(r"^(Bearer|Token)\s+", "", raw_token, flags=re.IGNORECASE).strip()
    provider_id = (stored.get("teamup_provider_id") or os.environ.get("TEAMUP_PROVIDER_ID") or TEAMUP_DEFAULT_PROVIDER_ID).strip()
    webhook_secret = (stored.get("teamup_webhook_secret") or os.environ.get("TEAMUP_WEBHOOK_SECRET") or "").strip()
    base_url = (stored.get("teamup_base_url") or os.environ.get("TEAMUP_BASE_URL") or TEAMUP_DEFAULT_BASE_URL).strip().rstrip("/")

    masked_token = ""
    if clean_token:
        if len(clean_token) > 8:
            masked_token = f"{clean_token[:4]}••••{clean_token[-4:]}"
        else:
            masked_token = "••••••••"

    return {
        "api_token": clean_token,
        "masked_token": masked_token,
        "has_token": bool(clean_token),
        "provider_id": provider_id,
        "webhook_secret": webhook_secret,
        "has_webhook_secret": bool(webhook_secret),
        "base_url": base_url,
        "configured": bool(clean_token),
    }


def save_teamup_setting(db, key, value):
    ensure_hyrox_tables(db)
    db.execute(
        "INSERT INTO hyrox_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
        (key, str(value or "").strip()),
    )


class TeamUpAPIError(Exception):
    def __init__(self, message, status_code=500, details=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def _build_ssl_context():
    """Build an SSLContext that works on macOS Python.org framework builds (/etc/ssl/cert.pem or certifi)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    for ca_path in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
        if os.path.exists(ca_path):
            try:
                return ssl.create_default_context(cafile=ca_path)
            except Exception:
                pass
    return ssl.create_default_context()


class TeamUpClient:
    """Official TeamUp API v2 HTTP Client (`https://goteamup.com/api/v2`)."""

    def __init__(self, api_token, provider_id="", base_url=TEAMUP_DEFAULT_BASE_URL, timeout=15, auth_scheme="Bearer"):
        clean_tok = re.sub(r"^(Bearer|Token)\s+", "", str(api_token or "").strip(), flags=re.IGNORECASE).strip()
        self.api_token = clean_tok
        self.provider_id = str(provider_id or "").strip()
        self.base_url = (base_url or TEAMUP_DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.auth_scheme = auth_scheme or "Bearer"

    def _headers(self, include_provider=True, scheme=None):
        if not self.api_token:
            raise TeamUpAPIError("TeamUp M2M API token is not configured.", status_code=400)
        active_scheme = scheme or self.auth_scheme or "Bearer"
        headers = {
            "Authorization": f"{active_scheme} {self.api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "TeamUp-Request-Mode": "provider",
            "User-Agent": "CSPerformance-HYROX/2.0",
        }
        if include_provider and self.provider_id:
            headers["TeamUp-Provider-ID"] = str(self.provider_id)
        return headers

    def _open_url(self, req):
        ctx = _build_ssl_context()
        try:
            return urllib.request.urlopen(req, timeout=self.timeout, context=ctx)
        except urllib.error.URLError as e:
            if "CERTIFICATE_VERIFY_FAILED" in str(e.reason) or isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
                unverified_ctx = ssl._create_unverified_context()
                return urllib.request.urlopen(req, timeout=self.timeout, context=unverified_ctx)
            raise

    def request(self, method, path, params=None, json_body=None, include_provider=True):
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        if params:
            clean_params = {k: v for k, v in params.items() if v is not None and v != ""}
            if clean_params:
                qs = urllib.parse.urlencode(clean_params)
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}{qs}"

        data_bytes = None
        if json_body is not None:
            data_bytes = json.dumps(json_body).encode("utf-8")

        schemes_to_try = [self.auth_scheme]
        alt_scheme = "Token" if self.auth_scheme == "Bearer" else "Bearer"
        if alt_scheme not in schemes_to_try:
            schemes_to_try.append(alt_scheme)

        last_err = None
        for idx, scheme in enumerate(schemes_to_try):
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers=self._headers(include_provider=include_provider, scheme=scheme),
                method=method.upper(),
            )
            try:
                with self._open_url(req) as resp:
                    self.auth_scheme = scheme
                    raw = resp.read().decode("utf-8", errors="replace")
                    return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError as e:
                err_body = ""
                try:
                    err_body = e.read().decode("utf-8", errors="replace")
                    parsed_err = json.loads(err_body)
                except Exception:
                    parsed_err = {"raw": err_body}
                last_err = TeamUpAPIError(
                    f"TeamUp API HTTP {e.code}: {err_body[:300]}",
                    status_code=e.code,
                    details=parsed_err,
                )
                if e.code in (401, 403) and idx == 0 and len(schemes_to_try) > 1:
                    continue
                raise last_err
            except urllib.error.URLError as e:
                raise TeamUpAPIError(f"TeamUp network error: {e.reason}", status_code=502)
        if last_err:
            raise last_err

    def fetch_all_pages(self, path, params=None, max_pages=10):
        """Iterate offset-paginated TeamUp v2 responses (`page` & `page_size=100`)."""
        params = dict(params or {})
        params.setdefault("page_size", 100)
        results = []
        for page_num in range(1, max_pages + 1):
            params["page"] = page_num
            payload = self.request("GET", path, params=params)
            if isinstance(payload, list):
                results.extend(payload)
                break
            page_items = payload.get("results") or []
            results.extend(page_items)
            if not payload.get("next") or not page_items:
                break
        return results

    def verify_application(self):
        """Call GET /api/v2/auth/application to verify M2M token and discover scoped_providers."""
        return self.request("GET", "/auth/application", include_provider=bool(self.provider_id))

    def list_events(self, starts_at_gte=None, starts_at_lte=None, query=None, offering_types=None):
        """Call GET /api/v2/events with optional date/query filters."""
        params = {
            "expand": "offering_type,instructors,venue",
            "page_size": 100,
        }
        if starts_at_gte:
            params["starts_at_gte"] = starts_at_gte
        if starts_at_lte:
            params["starts_at_lte"] = starts_at_lte
        if query:
            params["query"] = query
        if offering_types:
            params["offering_types"] = offering_types
        return self.fetch_all_pages("/events", params=params, max_pages=5)

    def list_attendances(self, event_ids=None, starts_at_gte=None, starts_at_lte=None, status="registered"):
        """Call GET /api/v2/attendances?expand=event,customer to pull registrations in 1 batched call."""
        params = {
            "expand": "event,customer",
            "sort": "event_starts_at",
            "page_size": 100,
        }
        if event_ids:
            if isinstance(event_ids, (list, tuple, set)):
                params["event"] = ",".join(str(x) for x in event_ids if x)
            else:
                params["event"] = str(event_ids)
        if starts_at_gte:
            params["event_starts_at_gte"] = starts_at_gte
        if starts_at_lte:
            params["event_starts_at_lte"] = starts_at_lte
        if status and status != "all":
            params["status"] = status
        return self.fetch_all_pages("/attendances", params=params, max_pages=10)

    def get_customer(self, customer_id):
        """Call GET /api/v2/customers/{id}."""
        return self.request("GET", f"/customers/{int(customer_id)}")

    def get_customer_field_values(self, customer_id=None):
        """Call GET /api/v2/customer_field_values to inspect custom fields (DOB, division, partner)."""
        params = {"page_size": 100}
        if customer_id:
            params["customer"] = int(customer_id)
        return self.fetch_all_pages("/customer_field_values", params=params, max_pages=3)


def map_teamup_attendance_to_entry(att_obj):
    """
    Transform a TeamUp v2 AttendanceRead object (with expanded `customer` and `event`
    or flat dictionary keys) into a normalized HYROX Sim entry payload.
    """
    if not isinstance(att_obj, dict):
        return None

    customer = att_obj.get("customer") if isinstance(att_obj.get("customer"), dict) else {}
    event_obj = att_obj.get("event") if isinstance(att_obj.get("event"), dict) else {}
    offering_obj = event_obj.get("offering_type") if isinstance(event_obj.get("offering_type"), dict) else {}

    # Customer ID
    customer_id = (
        customer.get("id")
        or (att_obj.get("customer") if isinstance(att_obj.get("customer"), (int, str)) else "")
        or att_obj.get("customer_id")
        or ""
    )

    # Full Name
    full_name = (
        customer.get("name")
        or customer.get("full_name")
        or f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
        or att_obj.get("customer_name")
        or att_obj.get("display_name")
        or att_obj.get("name")
        or ""
    ).strip()

    email = (customer.get("email") or att_obj.get("email") or "").strip().lower()

    # Inspect custom fields on customer or attendance if present
    custom_fields = {}
    raw_fields = (
        customer.get("custom_fields")
        or customer.get("field_values")
        or customer.get("fields")
        or att_obj.get("custom_fields")
        or []
    )
    if isinstance(raw_fields, dict):
        for k, v in raw_fields.items():
            custom_fields[re.sub(r"[^a-z0-9]+", "_", str(k).lower()).strip("_")] = str(v or "").strip()
    elif isinstance(raw_fields, list):
        for item in raw_fields:
            if isinstance(item, dict):
                fname = (
                    item.get("name")
                    or item.get("system_use")
                    or (item.get("field", {}).get("name") if isinstance(item.get("field"), dict) else "")
                    or (item.get("field", {}).get("system_use") if isinstance(item.get("field"), dict) else "")
                )
                fval = item.get("value") or item.get("display_value") or ""
                if fname:
                    custom_fields[re.sub(r"[^a-z0-9]+", "_", str(fname).lower()).strip("_")] = str(fval).strip()

    dob = (
        customer.get("date_of_birth")
        or customer.get("dob")
        or custom_fields.get("date_of_birth")
        or custom_fields.get("dob")
        or att_obj.get("dob")
        or ""
    )
    age_cat_raw = (
        customer.get("age_category")
        or custom_fields.get("age_category")
        or custom_fields.get("age_group")
        or dob
        or customer.get("age")
        or att_obj.get("age_category")
        or "30-34"
    )

    partner_name = (
        att_obj.get("partner_name")
        or custom_fields.get("partner_name")
        or custom_fields.get("partner")
        or custom_fields.get("doubles_partner")
        or custom_fields.get("teammate")
        or ""
    ).strip()

    # Gender fallback if event/offering name does not specify a HYROX division
    gender_raw = (
        customer.get("gender")
        or customer.get("sex")
        or custom_fields.get("gender")
        or custom_fields.get("sex")
        or att_obj.get("gender")
        or ""
    ).strip().lower()
    default_open_div = "women_open" if gender_raw in ("f", "female", "woman", "women", "w") else "men_open"

    # Division inference from custom field, offering name, event name, booking notes, or gender fallback
    explicit_div = (
        att_obj.get("division")
        or custom_fields.get("division")
        or custom_fields.get("hyrox_division")
        or custom_fields.get("category")
        or ""
    ).strip()
    event_or_offering_name = (
        offering_obj.get("name")
        or event_obj.get("name")
        or att_obj.get("offering_type_name")
        or att_obj.get("event_name")
        or ""
    ).strip()
    booking_notes_str = str(att_obj.get("notes") or att_obj.get("booking_notes") or "").strip()

    has_explicit_division = True
    if explicit_div:
        div_resolved = normalize_division(explicit_div)
    elif booking_notes_str and any(k in booking_notes_str.lower() for k in ("open", "pro", "double", "mixed", "women", "female", "men")):
        div_resolved = normalize_division(booking_notes_str)
    elif event_or_offering_name and any(k in event_or_offering_name.lower() for k in ("open", "pro", "double", "mixed", "women", "female", "men")):
        div_resolved = normalize_division(event_or_offering_name)
    elif partner_name:
        div_resolved = "mixed_doubles"
    else:
        div_resolved = default_open_div
        has_explicit_division = False

    # Wave / Heat time from event local_starts_at / starts_at or explicit heat_time
    raw_starts = (
        att_obj.get("heat_time")
        or event_obj.get("local_starts_at")
        or event_obj.get("starts_at")
        or att_obj.get("event_starts_at")
        or event_obj.get("name")
        or ""
    )
    heat_time = _normalize_heat_time_str(raw_starts)

    # Instructor / Volunteer fallback if event has instructors expanded
    volunteer = (att_obj.get("volunteer_name") or "").strip()
    instructors = event_obj.get("instructors")
    if not volunteer and isinstance(instructors, list) and instructors:
        first_inst = instructors[0]
        if isinstance(first_inst, dict):
            volunteer = (first_inst.get("name") or "").strip()

    att_status = str(att_obj.get("status") or "registered").strip().lower()
    notes_parts = []
    if att_obj.get("id"):
        notes_parts.append(f"TeamUp Attendance #{att_obj['id']}")
    if event_obj.get("id"):
        notes_parts.append(f"TeamUp Event #{event_obj['id']}")
    if att_obj.get("notes"):
        notes_parts.append(str(att_obj["notes"]).strip())

    return {
        "display_name": full_name,
        "partner_name": partner_name,
        "email": email,
        "dob": str(dob).strip(),
        "age_category": normalize_age_category(age_cat_raw),
        "division": div_resolved,
        "has_explicit_division": has_explicit_division,
        "has_explicit_age": bool(age_cat_raw or dob),
        "heat_time": heat_time,
        "volunteer_name": volunteer,
        "teamup_customer_id": str(customer_id).strip(),
        "teamup_attendance_status": att_status,
        "notes": " · ".join(notes_parts),
    }


@hyrox_bp.route("/api/hyrox/teamup/status", methods=["GET"])
def api_teamup_status():
    db = get_db()
    cfg = get_teamup_config(db)
    logs = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM hyrox_webhook_logs ORDER BY id DESC LIMIT 15"
        ).fetchall()
    ]
    return jsonify({
        "ok": True,
        "configured": cfg["configured"],
        "has_token": cfg["has_token"],
        "masked_token": cfg["masked_token"],
        "provider_id": cfg["provider_id"],
        "has_webhook_secret": cfg["has_webhook_secret"],
        "base_url": cfg["base_url"],
        "webhook_endpoint": "/api/hyrox/teamup/webhook",
        "supported_webhook_events": [
            "event_registration.created",
            "event_registration.removed",
            "event_registration.late_cancelled",
            "customer.created",
            "customer.updated",
        ],
        "api_spec": {
            "version": "v2 (OpenAPI 3.0.3)",
            "base_url": TEAMUP_DEFAULT_BASE_URL,
            "docs_url": "https://docs.goteamup.com",
            "schema_url": "https://goteamup.com/api/v2/schema/?format=json",
            "rate_limit": "250 requests / minute",
            "auth_header": "Authorization: Bearer <M2M_TOKEN>",
            "required_headers": ["TeamUp-Provider-ID", "TeamUp-Request-Mode: provider"],
        },
        "recent_webhooks": logs,
    })


@hyrox_bp.route("/api/hyrox/teamup/config", methods=["POST"])
def api_teamup_save_config():
    db = get_db()
    ensure_hyrox_tables(db)
    data = request.get_json(force=True) or {}

    if "api_token" in data and data["api_token"] is not None:
        tok = str(data["api_token"]).strip()
        if tok and "••••" not in tok:
            save_teamup_setting(db, "teamup_api_token", tok)
    if "provider_id" in data and data["provider_id"] is not None:
        save_teamup_setting(db, "teamup_provider_id", data["provider_id"])
    if "webhook_secret" in data and data["webhook_secret"] is not None:
        save_teamup_setting(db, "teamup_webhook_secret", data["webhook_secret"])
    if "base_url" in data and data["base_url"]:
        save_teamup_setting(db, "teamup_base_url", data["base_url"])

    db.commit()
    cfg = get_teamup_config(db)
    return jsonify({
        "ok": True,
        "configured": cfg["configured"],
        "has_token": cfg["has_token"],
        "masked_token": cfg["masked_token"],
        "provider_id": cfg["provider_id"],
        "has_webhook_secret": cfg["has_webhook_secret"],
        "base_url": cfg["base_url"],
    })


@hyrox_bp.route("/api/hyrox/teamup/test", methods=["POST"])
def api_teamup_test_connection():
    db = get_db()
    cfg = get_teamup_config(db)
    data = request.get_json(silent=True) or {}

    token = (data.get("api_token") or "").strip()
    if not token or "••••" in token:
        token = cfg["api_token"]
    provider_id = (data.get("provider_id") or cfg["provider_id"] or "").strip()

    if not token:
        return jsonify({
            "ok": False,
            "error": "No TeamUp M2M API token provided. Generate one in TeamUp -> Settings -> Integrations -> API Integration.",
        }), 400

    client = TeamUpClient(api_token=token, provider_id=provider_id, base_url=cfg["base_url"])
    try:
        save_teamup_setting(db, "teamup_api_token", token)
        if provider_id:
            save_teamup_setting(db, "teamup_provider_id", provider_id)
        db.commit()
        app_info = client.verify_application()
        scoped_providers = app_info.get("scoped_providers") or []
        if not provider_id and scoped_providers:
            first_prov = scoped_providers[0]
            provider_id = str(first_prov.get("id") if isinstance(first_prov, dict) else first_prov)
            save_teamup_setting(db, "teamup_provider_id", provider_id)
            db.commit()
        return jsonify({
            "ok": True,
            "application": app_info,
            "provider_id": provider_id,
            "scoped_providers": scoped_providers,
            "auth_scheme": client.auth_scheme,
        })
    except TeamUpAPIError as e:
        return jsonify({
            "ok": False,
            "error": e.message,
            "status_code": e.status_code,
            "details": e.details,
        }), e.status_code if 400 <= e.status_code < 600 else 502


@hyrox_bp.route("/api/hyrox/teamup/events", methods=["GET"])
def api_teamup_remote_events():
    db = get_db()
    cfg = get_teamup_config(db)
    if not cfg["has_token"]:
        return jsonify({
            "ok": False,
            "error": "TeamUp API token not configured yet.",
            "events": [],
        }), 400

    starts_gte = request.args.get("starts_at_gte") or request.args.get("date_from")
    starts_lte = request.args.get("starts_at_lte") or request.args.get("date_to")
    if starts_gte and len(starts_gte) == 10:
        starts_gte = f"{starts_gte}T00:00:00Z"
    if starts_lte and len(starts_lte) == 10:
        starts_lte = f"{starts_lte}T23:59:59Z"

    client = TeamUpClient(api_token=cfg["api_token"], provider_id=cfg["provider_id"], base_url=cfg["base_url"])
    try:
        events = client.list_events(
            starts_at_gte=starts_gte,
            starts_at_lte=starts_lte,
            query=request.args.get("query"),
            offering_types=request.args.get("offering_types"),
        )
        return jsonify({"ok": True, "count": len(events), "events": events})
    except TeamUpAPIError as e:
        return jsonify({"ok": False, "error": e.message, "details": e.details}), (
            e.status_code if 400 <= e.status_code < 600 else 502
        )


@hyrox_bp.route("/api/hyrox/events/<int:event_id>/sync-teamup", methods=["POST"])
def api_sync_teamup_to_event(event_id):
    """
    Sync registrations from TeamUp REST API v2 into the active HYROX Sim event.
    Supports either:
      1. Direct `attendances` JSON payload (matching GET /api/v2/attendances?expand=event,customer)
      2. Live pull from TeamUp API v2 using configured M2M token + provider ID.
    """
    db = get_db()
    ensure_hyrox_tables(db)
    ev = db.execute("SELECT * FROM hyrox_events WHERE id=?", (event_id,)).fetchone()
    if not ev:
        return jsonify({"error": "HYROX Event not found"}), 404

    data = request.get_json(silent=True) or {}
    attendances = data.get("attendances")
    if isinstance(data.get("results"), list) and attendances is None:
        attendances = data["results"]

    auto_stagger = bool(data.get("auto_stagger_slots"))
    stagger_start_time = (data.get("stagger_start_time") or "").strip()
    interval_mins = int(data.get("interval_mins") or ev["wave_interval_mins"] or 15)

    if attendances is None:
        inline_tok = (data.get("api_token") or "").strip()
        if inline_tok and "••••" not in inline_tok:
            save_teamup_setting(db, "teamup_api_token", inline_tok)
        inline_prov = (data.get("provider_id") or "").strip()
        if inline_prov:
            save_teamup_setting(db, "teamup_provider_id", inline_prov)
        if inline_tok or inline_prov:
            db.commit()
        cfg = get_teamup_config(db)
        if not cfg["has_token"]:
            return jsonify({
                "ok": False,
                "error": "TeamUp M2M API token is not configured. Save your token in the TeamUp API panel or pass an 'attendances' payload.",
            }), 400
        client = TeamUpClient(api_token=cfg["api_token"], provider_id=cfg["provider_id"], base_url=cfg["base_url"])
        teamup_event_ids = data.get("teamup_event_ids") or data.get("teamup_event_id")
        starts_gte = data.get("starts_at_gte")
        starts_lte = data.get("starts_at_lte")
        if not teamup_event_ids and not starts_gte:
            ev_date = ev["event_date"]
            ev_end = ev["event_end_date"] if "event_end_date" in ev.keys() and ev["event_end_date"] else ev_date
            starts_gte = f"{ev_date}T00:00:00Z"
            starts_lte = f"{ev_end}T23:59:59Z"
        try:
            attendances = client.list_attendances(
                event_ids=teamup_event_ids,
                starts_at_gte=starts_gte,
                starts_at_lte=starts_lte,
                status=data.get("status", "registered"),
            )
        except TeamUpAPIError as e:
            return jsonify({"ok": False, "error": e.message, "details": e.details}), (
                e.status_code if 400 <= e.status_code < 600 else 502
            )

    synced_ids = []
    cancelled_ids = []
    skipped = 0
    stagger_idx = 0

    for att in (attendances or []):
        mapped = map_teamup_attendance_to_entry(att)
        if not mapped or not mapped.get("display_name"):
            skipped += 1
            continue
        att_status = mapped.get("teamup_attendance_status", "registered")
        if att_status in ("late_cancelled", "not_registered", "cancelled", "removed"):
            existing = db.execute(
                "SELECT id, status FROM hyrox_entries WHERE event_id=? AND (LOWER(email)=? OR LOWER(display_name)=?) LIMIT 1",
                (event_id, mapped.get("email") or "__none__", mapped["display_name"].lower()),
            ).fetchone()
            if existing and existing["status"] == "scheduled":
                db.execute("UPDATE hyrox_entries SET status='dns', updated_at=CURRENT_TIMESTAMP WHERE id=?", (existing["id"],))
                cancelled_ids.append(existing["id"])
            else:
                skipped += 1
            continue

        if auto_stagger:
            base_hm = stagger_start_time or mapped.get("heat_time") or "08:00"
            m_hm = re.match(r"^(\d{1,2}):(\d{2})$", base_hm)
            base_mins = (int(m_hm.group(1)) * 60 + int(m_hm.group(2))) if m_hm else 8 * 60
            slot_mins = base_mins + (stagger_idx * interval_mins)
            mapped["heat_time"] = f"{(slot_mins // 60) % 24:02d}:{slot_mins % 60:02d}"
            stagger_idx += 1

        eid, err = _create_entry_record(db, event_id, mapped, upsert=True)
        if eid:
            synced_ids.append(eid)
        else:
            skipped += 1

    db.commit()
    return jsonify({
        "ok": True,
        "synced_count": len(synced_ids),
        "cancelled_count": len(cancelled_ids),
        "skipped_count": skipped,
        "synced_entry_ids": synced_ids,
        "cancelled_entry_ids": cancelled_ids,
    })


@hyrox_bp.route("/api/hyrox/teamup/webhook", methods=["POST"])
def api_teamup_webhook():
    """
    Official TeamUp API v2 Webhook Receiver.
    - Deduplicates via `TEAMUP-WEBHOOK-ID` header (TeamUp retries up to 5 times).
    - Validates optional `?secret=` query param or `X-TeamUp-Webhook-Secret` header.
    - Processes `feed_items`:
        * `event_registration.created`
        * `event_registration.removed`
        * `event_registration.late_cancelled`
        * `customer.created` / `customer.updated`
    - Responds with 200 OK within 10s as required by TeamUp webhook spec.
    """
    db = get_db()
    cfg = get_teamup_config(db)

    if cfg["webhook_secret"]:
        provided_secret = (
            request.args.get("secret")
            or request.headers.get("X-TeamUp-Webhook-Secret")
            or ""
        ).strip()
        if provided_secret != cfg["webhook_secret"]:
            return jsonify({"ok": False, "error": "Invalid webhook secret"}), 403

    webhook_id = (
        request.headers.get("TEAMUP-WEBHOOK-ID")
        or request.headers.get("Teamup-Webhook-Id")
        or ""
    ).strip()

    if webhook_id:
        dup = db.execute(
            "SELECT id FROM hyrox_webhook_logs WHERE webhook_id=? LIMIT 1",
            (webhook_id,)
        ).fetchone()
        if dup:
            return jsonify({"ok": True, "deduplicated": True, "webhook_id": webhook_id}), 200

    payload = request.get_json(silent=True) or {}
    feed_items = payload.get("feed_items") or []
    target_event_id = get_active_event_id(db, request.args.get("event_id", type=int) or payload.get("hyrox_event_id"))

    processed_items = []
    for idx, item in enumerate(feed_items):
        if not isinstance(item, dict):
            continue
        ftype = str(item.get("type") or "").strip()
        fid = str(item.get("id") or f"{idx + 1}")
        resources = item.get("resources") if isinstance(item.get("resources"), dict) else {}
        cust_id = str(resources.get("customer") or "")
        tu_event_id = str(resources.get("event") or "")
        action_summary = f"Received {ftype}"

        # If inline attendance/customer data is included or API token is configured, sync immediately
        inline_att = item.get("attendance") or (
            {"customer": item.get("customer"), "event": item.get("event")}
            if isinstance(item.get("customer"), dict)
            else None
        )

        if ftype in ("event_registration.removed", "event_registration.late_cancelled"):
            if cust_id and target_event_id:
                ath = db.execute(
                    "SELECT id FROM hyrox_athletes WHERE teamup_customer_id=? LIMIT 1",
                    (cust_id,)
                ).fetchone()
                if ath:
                    db.execute(
                        "UPDATE hyrox_entries SET status='dns', updated_at=CURRENT_TIMESTAMP "
                        "WHERE event_id=? AND athlete_id=? AND status='scheduled'",
                        (target_event_id, ath["id"]),
                    )
                    action_summary = f"Marked customer #{cust_id} entry as DNS ({ftype})"
        elif ftype == "event_registration.created" and target_event_id:
            mapped = None
            if inline_att:
                mapped = map_teamup_attendance_to_entry(inline_att)
            elif cfg["has_token"] and cust_id and tu_event_id:
                try:
                    client = TeamUpClient(api_token=cfg["api_token"], provider_id=cfg["provider_id"], base_url=cfg["base_url"])
                    atts = client.list_attendances(event_ids=[tu_event_id], status="all")
                    for a in atts:
                        c_obj = a.get("customer")
                        cid = str(c_obj.get("id") if isinstance(c_obj, dict) else c_obj)
                        if cid == cust_id:
                            mapped = map_teamup_attendance_to_entry(a)
                            break
                except TeamUpAPIError as e:
                    action_summary = f"Deferred fetch ({e.message})"
            if mapped and mapped.get("display_name"):
                eid, _ = _create_entry_record(db, target_event_id, mapped, upsert=True)
                if eid:
                    action_summary = f"Synced entry #{eid} ({mapped['display_name']})"
        elif ftype in ("customer.created", "customer.updated"):
            cust_obj = item.get("customer") if isinstance(item.get("customer"), dict) else None
            if not cust_obj and cfg["has_token"] and cust_id:
                try:
                    client = TeamUpClient(api_token=cfg["api_token"], provider_id=cfg["provider_id"], base_url=cfg["base_url"])
                    cust_obj = client.get_customer(cust_id)
                except TeamUpAPIError:
                    cust_obj = None
            if isinstance(cust_obj, dict):
                cname = (cust_obj.get("name") or f"{cust_obj.get('first_name', '')} {cust_obj.get('last_name', '')}").strip()
                if cname:
                    aid = find_or_create_athlete(
                        db,
                        full_name=cname,
                        email=cust_obj.get("email") or "",
                        dob=cust_obj.get("date_of_birth") or "",
                        age_category=normalize_age_category(cust_obj.get("date_of_birth") or cust_obj.get("age")),
                        teamup_customer_id=cust_id or str(cust_obj.get("id") or ""),
                    )
                    action_summary = f"Updated athlete #{aid} ({cname})"

        log_wid = f"{webhook_id}:{fid}" if (webhook_id and len(feed_items) > 1) else (webhook_id or f"wh-{int(time.time()*1000)}-{idx}")
        db.execute(
            "INSERT INTO hyrox_webhook_logs (webhook_id, feed_item_id, feed_item_type, customer_id, teamup_event_id, status, summary) "
            "VALUES (?, ?, ?, ?, ?, 'processed', ?)",
            (log_wid, fid, ftype, cust_id, tu_event_id, action_summary),
        )
        processed_items.append({"id": fid, "type": ftype, "summary": action_summary})

    if not feed_items and webhook_id:
        db.execute(
            "INSERT INTO hyrox_webhook_logs (webhook_id, feed_item_type, status, summary) VALUES (?, 'ping', 'processed', 'Webhook ping received')",
            (webhook_id,),
        )

    db.commit()
    return jsonify({
        "ok": True,
        "deduplicated": False,
        "webhook_id": webhook_id,
        "processed_count": len(processed_items),
        "processed": processed_items,
    }), 200

