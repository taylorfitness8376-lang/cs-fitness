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
    tokens = set(s.split("_"))
    is_female = bool(tokens & {"women", "womens", "woman", "female", "females", "ladies", "lady", "w", "f"}) or ("women" in s or "female" in s or "ladies" in s)
    is_male = (bool(tokens & {"men", "mens", "man", "male", "males", "m"}) or ("male" in s)) and not is_female
    is_double = bool(tokens & {"double", "doubles", "pair", "pairs", "dbl", "team", "partner"}) or ("double" in s or "pair" in s or "dbl" in s)
    is_pro = bool(tokens & {"pro", "pros"})
    has_mixed = bool(tokens & {"mixed", "mix"}) or ("mixed" in s)
    # If string says both 'male doubles' and 'mixed doubles' (e.g. a combined Saturday session title),
    # default to men_doubles unless only mixed is specified
    if has_mixed and not ("male_double" in s or "men_double" in s or "male_pair" in s or "men_pair" in s or ("male" in tokens and is_double)):
        return "mixed_doubles"
    if is_female and is_pro and is_double:
        return "women_pro_doubles"
    if is_male and is_pro and is_double:
        return "men_pro_doubles"
    if is_female and is_double:
        return "women_doubles"
    if is_male and is_double:
        return "men_doubles"
    if has_mixed:
        return "mixed_doubles"
    if is_female and is_pro:
        return "women_pro"
    if is_female:
        return "women_open"
    if is_male and is_pro:
        return "men_pro"
    if is_double:
        return "mixed_doubles"
    return "men_open"


HYROX_SIGNUP_GROUPS = {
    "male_solo": {
        "key": "male_solo",
        "order": 1,
        "number": 1,
        "label": "1. Male Solo",
        "short_label": "1. Male Solo",
        "day_number": 1,
        "day_label": "Saturday (Day 1)",
        "time_window": "14:00–17:00",
        "default_start_time": "14:00",
        "default_end_time": "15:20",
        "default_division": "men_open",
        "divisions": ["men_open", "men_pro"],
        "color": "#38bdf8",
    },
    "male_mixed_doubles": {
        "key": "male_mixed_doubles",
        "order": 2,
        "number": 2,
        "label": "2. Male Doubles / Mixed Doubles",
        "short_label": "2. Male / Mixed Doubles",
        "day_number": 1,
        "day_label": "Saturday (Day 1)",
        "time_window": "14:00–17:00",
        "default_start_time": "15:30",
        "default_end_time": "17:00",
        "default_division": "men_doubles",
        "divisions": ["men_doubles", "mixed_doubles", "men_pro_doubles"],
        "color": "#a855f7",
    },
    "female_solo": {
        "key": "female_solo",
        "order": 3,
        "number": 3,
        "label": "3. Female Solo",
        "short_label": "3. Female Solo",
        "day_number": 2,
        "day_label": "Sunday (Day 2)",
        "time_window": "09:30–14:00",
        "default_start_time": "10:00",
        "default_end_time": "11:50",
        "default_division": "women_open",
        "divisions": ["women_open", "women_pro"],
        "color": "#f472b6",
    },
    "female_doubles": {
        "key": "female_doubles",
        "order": 4,
        "number": 4,
        "label": "4. Female Doubles",
        "short_label": "4. Female Doubles",
        "day_number": 2,
        "day_label": "Sunday (Day 2)",
        "time_window": "09:30–14:00",
        "default_start_time": "12:00",
        "default_end_time": "14:00",
        "default_division": "women_doubles",
        "divisions": ["women_doubles", "women_pro_doubles"],
        "color": "#fb7185",
    },
}


def division_to_signup_group_key(division_key):
    div = normalize_division(division_key)
    if div in ("women_doubles", "women_pro_doubles"):
        return "female_doubles"
    if div in ("women_open", "women_pro"):
        return "female_solo"
    if div in ("men_doubles", "mixed_doubles", "men_pro_doubles"):
        return "male_mixed_doubles"
    return "male_solo"


def build_signup_groups_summary(items):
    """Group serialized entries or mapped TeamUp sign-ups into the 4 weekend sign-up buckets."""
    buckets = {}
    for g_key, g_meta in HYROX_SIGNUP_GROUPS.items():
        div_ref = HYROX_DIVISIONS.get(g_meta["default_division"], {})
        buckets[g_key] = {
            **g_meta,
            "weight_summary": div_ref.get("weight_summary", ""),
            "count": 0,
            "entries": [],
        }
    for item in (items or []):
        g_key = item.get("signup_group") or division_to_signup_group_key(item.get("division"))
        if g_key not in buckets:
            g_key = "male_solo"
        buckets[g_key]["entries"].append(item)
        buckets[g_key]["count"] = len(buckets[g_key]["entries"])
    return [buckets["male_solo"], buckets["male_mixed_doubles"], buckets["female_solo"], buckets["female_doubles"]]


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
            wall_ball_unbroken  INTEGER NOT NULL DEFAULT 0,
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

    entry_cols = {r["name"] for r in db.execute("PRAGMA table_info(hyrox_entries)").fetchall()}
    for col_name, col_def in [
        ("wall_ball_unbroken", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        if col_name not in entry_cols:
            db.execute(f"ALTER TABLE hyrox_entries ADD COLUMN {col_name} {col_def}")

    count = db.execute("SELECT COUNT(*) as c FROM hyrox_events").fetchone()["c"]
    if count == 0:
        seed_default_hyrox_data(db)
        db.commit()
    else:
        _purge_legacy_sample_data(db)


def _purge_non_sim_teamup_entries(db, event_id=None):
    """
    Remove any entries in `hyrox_entries` that were accidentally synced from regular
    non-simulation gym classes on Saturday/Sunday (e.g., 'Hot Strength & Ergs' [30 people],
    'Hyrox Youngstars specific training (age 8-16)' [2 people], 'Thresholds',
    'Strength & conditioning', 'NXTGen little legends', or 'Hyrox Specific Training').
    """
    non_sim_patterns = (
        "%hot strength%",
        "%youngstars%",
        "%little legends%",
        "%nxtgen%",
        "%thresholds%",
        "%strength & conditioning%",
        "%specific training%",
        "%teamup event #111112517%",
        "%teamup event #104498152%",
        "%teamup event #104505072%",
        "%teamup event #104498108%",
        "%teamup event #110290059%",
        "%teamup event #104756703%",
    )
    where_clauses = " OR ".join("LOWER(COALESCE(notes, '')) LIKE ?" for _ in non_sim_patterns)
    params = list(non_sim_patterns)
    sql = f"SELECT id FROM hyrox_entries WHERE ({where_clauses})"
    if event_id is not None:
        sql += " AND event_id=?"
        params.append(event_id)
    bad_rows = db.execute(sql, params).fetchall()
    if not bad_rows:
        return 0
    bad_ids = [r["id"] for r in bad_rows]
    placeholders = ",".join("?" for _ in bad_ids)
    db.execute(f"DELETE FROM hyrox_splits WHERE entry_id IN ({placeholders})", bad_ids)
    db.execute(f"DELETE FROM hyrox_entries WHERE id IN ({placeholders})", bad_ids)
    return len(bad_ids)


def _purge_legacy_sample_data(db):
    """
    Remove legacy pre-seeded sample events ('CS Performance HYROX Baseline Sim — Sep 2026'),
    sample entries (@example.com or demo judge PINs 1101..1203 / 9101..9103), sample athletes
    (TU-1001..TU-1013), and any non-simulation regular gym class entries ('Hot Strength & Ergs',
    'Hyrox Youngstars', 'Thresholds', 'Hyrox Specific Training') so only actual HYROX Simulation
    sign-ups remain.
    """
    changed = False

    # 0. One-time clean-slate reset for the Saturday 28th & Sunday 29th setup so any deployed DB
    #    with old demo/synced test rows starts completely empty (0 entries).
    clean_flag = db.execute(
        "SELECT value FROM hyrox_settings WHERE key='clean_slate_sat28_sun29_v1'"
    ).fetchone()
    if not clean_flag:
        db.execute("DELETE FROM hyrox_splits")
        db.execute("DELETE FROM hyrox_entries")
        db.execute("DELETE FROM hyrox_athletes")
        db.execute("DELETE FROM hyrox_heats")
        db.execute("DELETE FROM hyrox_events")
        db.execute(
            "INSERT INTO hyrox_settings (key, value, updated_at) VALUES ('clean_slate_sat28_sun29_v1', '1', CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value='1', updated_at=CURRENT_TIMESTAMP"
        )
        seed_default_hyrox_data(db)
        db.commit()
        return

    # 0b. Always purge any non-simulation regular gym class attendances (e.g. Hot Strength & Ergs,
    #     Youngstars, Thresholds, Specific Training) that were pulled before class filtering.
    if _purge_non_sim_teamup_entries(db) > 0:
        changed = True

    # 1. Remove the seeded September 2026 baseline demo event if present
    sep_events = db.execute(
        "SELECT id FROM hyrox_events WHERE name LIKE '%Baseline Sim — Sep 2026%'"
    ).fetchall()
    for ev in sep_events:
        eid = ev["id"]
        db.execute("DELETE FROM hyrox_splits WHERE entry_id IN (SELECT id FROM hyrox_entries WHERE event_id=?)", (eid,))
        db.execute("DELETE FROM hyrox_entries WHERE event_id=?", (eid,))
        db.execute("DELETE FROM hyrox_heats WHERE event_id=?", (eid,))
        db.execute("DELETE FROM hyrox_events WHERE id=?", (eid,))
        changed = True

    # 2. Remove seeded demo entries (linked to sample athletes TU-1001..TU-1013)
    demo_entries = db.execute(
        "SELECT e.id, e.event_id FROM hyrox_entries e "
        "LEFT JOIN hyrox_athletes a ON e.athlete_id = a.id "
        "WHERE a.teamup_customer_id LIKE 'TU-10%'"
    ).fetchall()
    if demo_entries:
        demo_ids = [r["id"] for r in demo_entries]
        placeholders = ",".join("?" for _ in demo_ids)
        db.execute(f"DELETE FROM hyrox_splits WHERE entry_id IN ({placeholders})", demo_ids)
        db.execute(f"DELETE FROM hyrox_entries WHERE id IN ({placeholders})", demo_ids)
        changed = True

    # 3. Remove seeded demo athletes (TU-1001..TU-1013)
    cur_del_ath = db.execute(
        "DELETE FROM hyrox_athletes WHERE teamup_customer_id LIKE 'TU-10%'"
    )
    if cur_del_ath.rowcount:
        changed = True

    # 4. Upgrade any legacy Nov 2026 event date (2026-11-14) to Saturday 28th & Sunday 29th (2026-11-28 / 2026-11-29)
    legacy_nov = db.execute(
        "SELECT id, event_date FROM hyrox_events WHERE name LIKE 'CS Performance HYROX Sim —%Nov 2026%' LIMIT 1"
    ).fetchone()
    if legacy_nov and legacy_nov["event_date"] == "2026-11-14":
        db.execute(
            "UPDATE hyrox_events SET name=?, event_date='2026-11-28', end_date='2026-11-29', num_days=2, "
            "lanes_per_wave=1, wave_interval_mins=10, transition_buffer_mins=10 WHERE id=?",
            ("CS Performance HYROX Sim — Sat 28th & Sun 29th Nov 2026", legacy_nov["id"]),
        )
        db.execute("UPDATE hyrox_heats SET slot_date='2026-11-28' WHERE event_id=? AND COALESCE(day_number, 1)=1", (legacy_nov["id"],))
        db.execute("UPDATE hyrox_heats SET slot_date='2026-11-29' WHERE event_id=? AND COALESCE(day_number, 1)=2", (legacy_nov["id"],))
        changed = True

    # 5. Reset empty heats from 'completed'/'racing' back to 'scheduled'
    cur_reset_heats = db.execute(
        "UPDATE hyrox_heats SET status='scheduled' WHERE status != 'scheduled' "
        "AND id NOT IN (SELECT DISTINCT heat_id FROM hyrox_entries WHERE heat_id IS NOT NULL)"
    )
    if cur_reset_heats.rowcount:
        changed = True

    # 6. If all events were removed, seed the clean empty Saturday 28th & Sunday 29th event
    rem_events = db.execute("SELECT COUNT(*) as c FROM hyrox_events").fetchone()["c"]
    if rem_events == 0:
        seed_default_hyrox_data(db)
        changed = True

    is_testing = False
    try:
        from flask import has_app_context, current_app
        is_testing = bool(has_app_context() and current_app.config.get("TESTING"))
    except Exception:
        is_testing = False

    if not is_testing:
        seeded_13_flag = db.execute(
            "SELECT value FROM hyrox_settings WHERE key='confirmed_sat28_sun29_13_roster_v1'"
        ).fetchone()
        if not seeded_13_flag:
            _seed_confirmed_sat28_sun29_signups(db)
            db.execute(
                "INSERT INTO hyrox_settings (key, value, updated_at) VALUES ('confirmed_sat28_sun29_13_roster_v1', '1', CURRENT_TIMESTAMP) "
                "ON CONFLICT(key) DO UPDATE SET value='1', updated_at=CURRENT_TIMESTAMP"
            )
            changed = True

        five_min_flag = db.execute(
            "SELECT value FROM hyrox_settings WHERE key='five_min_slots_sat28_sun29_v1'"
        ).fetchone()
        if not five_min_flag:
            ev_latest = db.execute(
                "SELECT id, event_date, end_date FROM hyrox_events ORDER BY event_date DESC, id DESC LIMIT 1"
            ).fetchone()
            if ev_latest:
                _ensure_5min_weekend_heats(
                    db,
                    ev_latest["id"],
                    sat_date=ev_latest["event_date"] or "2026-11-28",
                    sun_date=ev_latest["end_date"] or "2026-11-29",
                    repack_entries=False,
                )
            db.execute(
                "INSERT INTO hyrox_settings (key, value, updated_at) VALUES ('five_min_slots_sat28_sun29_v1', '1', CURRENT_TIMESTAMP) "
                "ON CONFLICT(key) DO UPDATE SET value='1', updated_at=CURRENT_TIMESTAMP"
            )
            changed = True

        joe_wardle_flag = db.execute(
            "SELECT value FROM hyrox_settings WHERE key='joe_wardle_solo_fix_v1'"
        ).fetchone()
        if not joe_wardle_flag:
            jw_rows = db.execute(
                "SELECT id, event_id, heat_id, division, partner_name FROM hyrox_entries "
                "WHERE LOWER(TRIM(display_name))='joe wardle'"
            ).fetchall()
            for jw in jw_rows:
                if (jw["partner_name"] or "").strip().upper().startswith("TBC") or jw["division"] == "men_doubles":
                    db.execute(
                        "UPDATE hyrox_entries SET division='men_open', partner_name='', partner_athlete_id=NULL, "
                        "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (jw["id"],),
                    )
            db.execute(
                "INSERT INTO hyrox_settings (key, value, updated_at) VALUES ('joe_wardle_solo_fix_v1', '1', CURRENT_TIMESTAMP) "
                "ON CONFLICT(key) DO UPDATE SET value='1', updated_at=CURRENT_TIMESTAMP"
            )
            changed = True

        screenshot_restore_flag = db.execute(
            "SELECT value FROM hyrox_settings WHERE key='confirmed_screenshot_volunteers_and_slots_v1'"
        ).fetchone()
        if not screenshot_restore_flag:
            _restore_screenshot_volunteers_and_slots(db)
            db.execute(
                "INSERT INTO hyrox_settings (key, value, updated_at) VALUES ('confirmed_screenshot_volunteers_and_slots_v1', '1', CURRENT_TIMESTAMP) "
                "ON CONFLICT(key) DO UPDATE SET value='1', updated_at=CURRENT_TIMESTAMP"
            )
            changed = True

        sunday_0930_flag = db.execute(
            "SELECT value FROM hyrox_settings WHERE key='sunday_0930_slots_v1'"
        ).fetchone()
        if not sunday_0930_flag:
            ev_rows = db.execute(
                "SELECT id, event_date, end_date FROM hyrox_events ORDER BY event_date DESC, id DESC"
            ).fetchall()
            for ev_r in ev_rows:
                _ensure_5min_weekend_heats(
                    db,
                    ev_r["id"],
                    sat_date=ev_r["event_date"] or "2026-11-28",
                    sun_date=ev_r["end_date"] or "2026-11-29",
                    repack_entries=False,
                )
            db.execute(
                "INSERT INTO hyrox_settings (key, value, updated_at) VALUES ('sunday_0930_slots_v1', '1', CURRENT_TIMESTAMP) "
                "ON CONFLICT(key) DO UPDATE SET value='1', updated_at=CURRENT_TIMESTAMP"
            )
            changed = True

    if changed:
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


# ── Clean Default Weekend Event (Zero Sample Athletes / Entries) ─────────────

def _ensure_5min_weekend_heats(db, event_id, sat_date="2026-11-28", sun_date="2026-11-29", repack_entries=False):
    """
    Ensure 5-minute 1:1 heat slots exist across all 4 weekend blocks:
      - Day 1 (Sat) 14:00–15:20: 1. Male Solo (5m slots)
      - Day 1 (Sat) 15:30–16:55: 2. Male / Mixed Doubles (5m slots)
      - Day 2 (Sun) 09:30–11:50: 3. Female Solo (5m slots)
      - Day 2 (Sun) 12:00–13:55: 4. Female Doubles (5m slots)
    Optionally repacks scheduled entries sequentially into 5-minute slots within each group.
    """
    db.execute("UPDATE hyrox_events SET wave_interval_mins=5 WHERE id=?", (event_id,))
    blocks = [
        (1, sat_date, "men_open",      "14:00", "15:20", "1. Male Solo"),
        (1, sat_date, "men_doubles",   "15:30", "16:55", "2. Male / Mixed Doubles"),
        (2, sun_date, "women_open",    "09:30", "11:50", "3. Female Solo"),
        (2, sun_date, "women_doubles", "12:00", "13:55", "4. Female Doubles"),
    ]
    for day_num, s_date, div_blk, start_hm, end_hm, grp_label in blocks:
        sh, sm = (int(x) for x in start_hm.split(":"))
        eh, em = (int(x) for x in end_hm.split(":"))
        cur_m = sh * 60 + sm
        end_m = eh * 60 + em
        while cur_m <= end_m:
            t_str = f"{cur_m // 60:02d}:{cur_m % 60:02d}"
            h_name = f"Day {day_num} · {t_str} — {grp_label}"
            buf_m = 10 if cur_m == end_m else 0
            existing = db.execute(
                "SELECT id FROM hyrox_heats WHERE event_id=? AND COALESCE(day_number, 1)=? AND start_time=? LIMIT 1",
                (event_id, day_num, t_str),
            ).fetchone()
            if existing:
                db.execute(
                    "UPDATE hyrox_heats SET slot_date=?, division_block=?, name=?, max_lanes=1 WHERE id=?",
                    (s_date, div_blk, h_name, existing["id"]),
                )
            else:
                max_h = db.execute(
                    "SELECT COALESCE(MAX(heat_number), 0) as m FROM hyrox_heats WHERE event_id=?",
                    (event_id,),
                ).fetchone()["m"]
                db.execute(
                    "INSERT INTO hyrox_heats (event_id, heat_number, day_number, slot_date, division_block, transition_buffer_mins, name, start_time, max_lanes, status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'scheduled')",
                    (event_id, max_h + 1, day_num, s_date, div_blk, buf_m, h_name, t_str),
                )
            cur_m += 5

    ordered_heats = db.execute(
        "SELECT id FROM hyrox_heats WHERE event_id=? ORDER BY COALESCE(day_number, 1) ASC, start_time ASC, id ASC",
        (event_id,),
    ).fetchall()
    for idx, hr in enumerate(ordered_heats, start=1):
        db.execute("UPDATE hyrox_heats SET heat_number=? WHERE id=?", (idx, hr["id"]))

    if repack_entries:
        entries = db.execute(
            "SELECT e.id, e.division, e.status, COALESCE(h.start_time, '99:99') as st "
            "FROM hyrox_entries e LEFT JOIN hyrox_heats h ON e.heat_id=h.id "
            "WHERE e.event_id=? ORDER BY st ASC, e.id ASC",
            (event_id,),
        ).fetchall()
        group_buckets = {"male_solo": [], "male_mixed_doubles": [], "female_solo": [], "female_doubles": []}
        for er in entries:
            g_key = division_to_signup_group_key(er["division"])
            group_buckets.setdefault(g_key, []).append(er)

        group_windows = {
            "male_solo":          (1, "14:00", "15:25"),
            "male_mixed_doubles": (1, "15:30", "16:55"),
            "female_solo":        (2, "10:00", "11:55"),
            "female_doubles":     (2, "12:00", "13:55"),
        }
        for g_key, g_entries in group_buckets.items():
            if not g_entries or g_key not in group_windows:
                continue
            day_num, w_start, w_end = group_windows[g_key]
            avail_heats = db.execute(
                "SELECT id FROM hyrox_heats WHERE event_id=? AND COALESCE(day_number, 1)=? "
                "AND start_time >= ? AND start_time <= ? ORDER BY start_time ASC",
                (event_id, day_num, w_start, w_end),
            ).fetchall()
            for idx, er in enumerate(g_entries):
                if idx < len(avail_heats):
                    db.execute(
                        "UPDATE hyrox_entries SET heat_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (avail_heats[idx]["id"], er["id"]),
                    )


def seed_default_hyrox_data(db):
    """
    Create a clean, empty 2-Day HYROX Weekend Event for Saturday 28th (14:00–17:00)
    & Sunday 29th (10:00–14:00) with 5-minute 1:1 time slots across the 4 sign-up groups and
    NO sample athletes or entries.
    """
    cur_nov = db.execute(
        "INSERT INTO hyrox_events (name, event_date, end_date, num_days, venue, wave_interval_mins, lanes_per_wave, transition_buffer_mins, status, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "CS Performance HYROX Sim — Sat 28th & Sun 29th Nov 2026",
            "2026-11-28",
            "2026-11-29",
            2,
            "CS Performance Studio",
            5,
            1,
            10,
            "live",
            "Saturday 28th (14:00–17:00): 1. Male Solo & 2. Male Doubles / Mixed Doubles | Sunday 29th (10:00–14:00): 3. Female Solo & 4. Female Doubles.",
        ),
    )
    nov_event_id = cur_nov.lastrowid
    _ensure_5min_weekend_heats(db, nov_event_id, sat_date="2026-11-28", sun_date="2026-11-29", repack_entries=False)

    db.execute(
        "INSERT INTO hyrox_settings (key, value, updated_at) VALUES ('clean_slate_sat28_sun29_v1', '1', CURRENT_TIMESTAMP) "
        "ON CONFLICT(key) DO UPDATE SET value='1', updated_at=CURRENT_TIMESTAMP"
    )


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
    e["wall_ball_unbroken"] = bool(e.get("wall_ball_unbroken"))
    grp_key = division_to_signup_group_key(div_key)
    grp_meta = HYROX_SIGNUP_GROUPS[grp_key]
    e["signup_group"] = grp_key
    e["signup_group_label"] = grp_meta["label"]
    e["signup_group_number"] = grp_meta["number"]
    raw_notes = str(e.get("notes") or "").strip()
    if "TeamUp" in raw_notes and "·" in raw_notes:
        e["teamup_event_name"] = raw_notes.split("·")[0].strip()
    else:
        e["teamup_event_name"] = ""
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
    default_day_num = 1 if grp_meta["number"] in (1, 2) else 2
    e["heat_day_number"] = int(heat_dict.get("day_number") or default_day_num)
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
@hyrox_bp.route("/hyrox/start-list")
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


@hyrox_bp.route("/hyrox/manifest.json")
def hyrox_pwa_manifest():
    return jsonify({
        "name": "CS Performance HYROX Judge Timer",
        "short_name": "CS HYROX Timer",
        "description": "1:1 Volunteer Lane Judge Timer for CS Performance HYROX Race Simulations",
        "start_url": "/hyrox/judge",
        "scope": "/hyrox",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#040805",
        "theme_color": "#040805",
        "icons": [
            {
                "src": "/static/logo.jpg",
                "sizes": "192x192",
                "type": "image/jpeg",
            },
            {
                "src": "/static/logo.jpg",
                "sizes": "512x512",
                "type": "image/jpeg",
            },
        ],
    })


@hyrox_bp.route("/hyrox/sim-test")
def hyrox_sim_test_page():
    """
    4-Athlete Simultaneous Sim Test Lab:
    Runs 4 interactive Judge Timing Apps side-by-side + live TV Broadcast preview
    with 1-click view toggles and mock race controls (Start All 4, Mock Mid-Race,
    Advance All +1 Split, Reset All 4 to Scheduled).
    """
    db = get_db()
    ensure_hyrox_tables(db)
    event_id = get_active_event_id(db, request.args.get("event_id", type=int))

    entries = []
    default_entry_ids = []
    if event_id:
        erows = db.execute("SELECT * FROM hyrox_entries WHERE event_id=? ORDER BY id ASC", (event_id,)).fetchall()
        entries = [serialize_entry(db, r, include_splits=True, include_history=False) for r in erows]
        entries.sort(
            key=lambda x: (
                int(x.get("heat_day_number") or 1),
                x.get("heat_start_time") or "99:99",
                x.get("bib_number") or "999",
                x["id"],
            )
        )
        # Prefer Saturday Men's Solo entries first, then any solo entries, then any entries
        sat_solo = [
            e["id"]
            for e in entries
            if e.get("division") in ("men_open", "men_pro") and not (e.get("partner_name") or "").strip()
        ]
        any_solo = [
            e["id"]
            for e in entries
            if e.get("division") in ("men_open", "men_pro", "women_open", "women_pro")
            and not (e.get("partner_name") or "").strip()
            and e["id"] not in sat_solo
        ]
        other_ids = [e["id"] for e in entries if e["id"] not in sat_solo and e["id"] not in any_solo]
        default_entry_ids = (sat_solo + any_solo + other_ids)[:4]

    return render_template(
        "hyrox_sim_test.html",
        active_event_id=event_id,
        entries=entries,
        default_entry_ids=default_entry_ids,
        divisions=HYROX_DIVISIONS,
    )


@hyrox_bp.route("/api/hyrox/events/<int:event_id>/sim-test", methods=["POST"])
def api_sim_test_control(event_id):
    """
    Batch mock controller for testing multiple athletes racing simultaneously:
      - action='start_all': Reset splits & start all selected entries on Run 1 simultaneously
      - action='staggered_stages': Place the selected entries at different realistic stages of the race
      - action='advance_all': Advance each selected entry by +1 split with realistic split durations
      - action='reset_all': Reset selected entries back to 'scheduled' (00:00) for clean race day state
    """
    db = get_db()
    ensure_hyrox_tables(db)
    ev = db.execute("SELECT * FROM hyrox_events WHERE id=?", (event_id,)).fetchone()
    if not ev:
        return jsonify({"error": "Event not found"}), 404

    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "start_all").strip().lower()
    raw_ids = data.get("entry_ids") or []
    entry_ids = [int(x) for x in raw_ids if str(x).isdigit()]

    if not entry_ids:
        erows = db.execute("SELECT * FROM hyrox_entries WHERE event_id=? ORDER BY id ASC", (event_id,)).fetchall()
        all_entries = [serialize_entry(db, r, include_splits=False, include_history=False) for r in erows]
        all_entries.sort(
            key=lambda x: (
                int(x.get("heat_day_number") or 1),
                x.get("heat_start_time") or "99:99",
                x["id"],
            )
        )
        sat_solo = [
            e["id"]
            for e in all_entries
            if e.get("division") in ("men_open", "men_pro") and not (e.get("partner_name") or "").strip()
        ]
        any_solo = [
            e["id"]
            for e in all_entries
            if e.get("division") in ("men_open", "men_pro", "women_open", "women_pro")
            and not (e.get("partner_name") or "").strip()
            and e["id"] not in sat_solo
        ]
        other_ids = [e["id"] for e in all_entries if e["id"] not in sat_solo and e["id"] not in any_solo]
        entry_ids = (sat_solo + any_solo + other_ids)[:4]

    now_ms = int(time.time() * 1000)

    # Realistic split durations (ms) for 16 splits (1.2km runs ~4:45-5:10, stations ~2:20-4:15)
    mock_split_durations = {
        1: 285000,   # Run 1 (04:45)
        2: 248000,   # 1. SkiErg (04:08)
        3: 294000,   # Run 2 (04:54)
        4: 172000,   # 2. Sled Push (02:52)
        5: 302000,   # Run 3 (05:02)
        6: 215000,   # 3. Sled Pull (03:35)
        7: 308000,   # Run 4 (05:08)
        8: 252000,   # 4. Burpee Broad Jumps (04:12)
        9: 305000,   # Run 5 (05:05)
        10: 256000,  # 5. Row (04:16)
        11: 298000,  # Run 6 (04:58)
        12: 138000,  # 6. Farmers Carry (02:18)
        13: 304000,  # Run 7 (05:04)
        14: 244000,  # 7. Sandbag Lunges (04:04)
        15: 296000,  # Run 8 (04:56)
        16: 265000,  # 8. Wall Balls (04:25)
    }

    updated_entries = []
    for slot_idx, eid in enumerate(entry_ids):
        row = db.execute("SELECT * FROM hyrox_entries WHERE id=? AND event_id=?", (eid, event_id)).fetchone()
        if not row:
            continue
        ensure_entry_splits(db, eid)

        if action == "reset_all":
            db.execute(
                "UPDATE hyrox_splits SET duration_ms=NULL, completed_at_ms=NULL, edited_by='', notes='' WHERE entry_id=?",
                (eid,),
            )
            db.execute(
                "UPDATE hyrox_entries SET status='scheduled', started_at_ms=NULL, finished_at_ms=NULL, "
                "total_ms=NULL, run_total_ms=NULL, station_total_ms=NULL, penalty_ms=0, wall_ball_reps=0, "
                "wall_ball_unbroken=0, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (eid,),
            )

        elif action == "start_all":
            # Reset splits and start all 4 on Run 1 right now (with tiny 2s offset per lane so clocks look natural)
            start_ms = now_ms - (slot_idx * 2000)
            db.execute(
                "UPDATE hyrox_splits SET duration_ms=NULL, completed_at_ms=NULL, edited_by='', notes='' WHERE entry_id=?",
                (eid,),
            )
            db.execute(
                "UPDATE hyrox_entries SET status='racing', started_at_ms=?, finished_at_ms=NULL, "
                "total_ms=NULL, run_total_ms=NULL, station_total_ms=NULL, penalty_ms=0, wall_ball_reps=0, "
                "wall_ball_unbroken=0, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (start_ms, eid),
            )

        elif action in ("staggered_stages", "mock_mid_race"):
            # Put Athlete 1..4 on different stages:
            # Slot 0 -> Active on Split 4 (2. Sled Push) -> splits 1..3 completed
            # Slot 1 -> Active on Split 7 (Run 4) -> splits 1..6 completed
            # Slot 2 -> Active on Split 10 (5. Row) -> splits 1..9 completed
            # Slot 3 -> Active on Split 16 (8. Wall Balls, 45 reps) -> splits 1..15 completed
            completed_counts = [3, 6, 9, 15]
            done_n = completed_counts[slot_idx % len(completed_counts)]
            active_stage_elapsed_ms = 42000 + (slot_idx * 17000)
            jitter = (slot_idx - 1) * 4000

            durations = []
            for s_i in range(1, done_n + 1):
                dur = max(60000, mock_split_durations.get(s_i, 240000) + jitter)
                durations.append((s_i, dur))

            total_done_ms = sum(d for _, d in durations)
            start_ms = now_ms - total_done_ms - active_stage_elapsed_ms

            db.execute(
                "UPDATE hyrox_splits SET duration_ms=NULL, completed_at_ms=NULL, edited_by='', notes='' WHERE entry_id=?",
                (eid,),
            )
            cursor_ms = start_ms
            for s_i, dur in durations:
                cursor_ms += dur
                db.execute(
                    "UPDATE hyrox_splits SET duration_ms=?, completed_at_ms=?, edited_by='sim-test' "
                    "WHERE entry_id=? AND split_index=?",
                    (dur, cursor_ms, eid, s_i),
                )
            wb_reps = 45 if done_n == 15 else 0
            db.execute(
                "UPDATE hyrox_entries SET status='racing', started_at_ms=?, finished_at_ms=NULL, "
                "wall_ball_reps=?, wall_ball_unbroken=0, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (start_ms, wb_reps, eid),
            )
            recalculate_entry_totals(db, eid)

        elif action == "advance_all":
            # If scheduled, start them; if racing, complete their current split with a realistic time
            if not row["started_at_ms"] or row["status"] == "scheduled":
                start_ms = now_ms - (slot_idx * 2000)
                db.execute(
                    "UPDATE hyrox_entries SET status='racing', started_at_ms=?, finished_at_ms=NULL, "
                    "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (start_ms, eid),
                )
            else:
                next_sp = db.execute(
                    "SELECT * FROM hyrox_splits WHERE entry_id=? AND duration_ms IS NULL ORDER BY split_index ASC LIMIT 1",
                    (eid,),
                ).fetchone()
                if next_sp:
                    s_idx = int(next_sp["split_index"])
                    jitter = (slot_idx - 1) * 3000
                    dur = max(45000, mock_split_durations.get(s_idx, 240000) + jitter)
                    # Shift started_at_ms back by `dur` so elapsed clocks stay continuous with `now_ms`
                    prev_done = db.execute(
                        "SELECT COALESCE(SUM(duration_ms), 0) as s FROM hyrox_splits WHERE entry_id=? AND duration_ms IS NOT NULL",
                        (eid,),
                    ).fetchone()["s"]
                    new_start_ms = now_ms - int(prev_done) - dur
                    db.execute(
                        "UPDATE hyrox_entries SET started_at_ms=? WHERE id=?",
                        (new_start_ms, eid),
                    )
                    db.execute(
                        "UPDATE hyrox_splits SET duration_ms=?, completed_at_ms=?, edited_by='sim-test' "
                        "WHERE entry_id=? AND split_index=?",
                        (dur, now_ms, eid, s_idx),
                    )
                    recalculate_entry_totals(db, eid)

        refreshed = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (eid,)).fetchone()
        updated_entries.append(serialize_entry(db, refreshed, include_splits=True, include_history=False))

    db.commit()
    return jsonify({
        "ok": True,
        "action": action,
        "entry_ids": entry_ids,
        "entries": updated_entries,
        "server_time_ms": int(time.time() * 1000),
    })


@hyrox_bp.route("/hyrox/judge")
def hyrox_judge_page():
    db = get_db()
    ensure_hyrox_tables(db)
    entry_id = request.args.get("entry", type=int) or request.args.get("entry_id", type=int)
    event_id = get_active_event_id(db, request.args.get("event_id", type=int))

    initial_entry_data = None
    if entry_id:
        erow = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
        if erow:
            event_id = erow["event_id"]
            initial_entry_data = serialize_entry(db, erow, include_splits=True, include_history=False)

    initial_heats = []
    initial_entries = []
    if event_id:
        initial_heats = [
            dict(h)
            for h in db.execute(
                "SELECT * FROM hyrox_heats WHERE event_id=? ORDER BY day_number ASC, start_time ASC, heat_number ASC",
                (event_id,),
            ).fetchall()
        ]
        erows = db.execute("SELECT * FROM hyrox_entries WHERE event_id=? ORDER BY id ASC", (event_id,)).fetchall()
        initial_entries = [serialize_entry(db, r, include_splits=True, include_history=False) for r in erows]
        initial_entries.sort(
            key=lambda x: (
                int(x.get("heat_day_number") or 1),
                x.get("heat_start_time") or "99:99",
                x.get("bib_number") or "999",
                x["id"],
            )
        )

    return render_template(
        "hyrox_judge.html",
        initial_entry_id=entry_id,
        active_event_id=event_id,
        initial_entry_data=initial_entry_data,
        initial_heats=initial_heats,
        initial_entries=initial_entries,
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


@hyrox_bp.route("/hyrox/tv/finisher")
def hyrox_tv_finisher_page():
    db = get_db()
    ensure_hyrox_tables(db)
    entry_id = request.args.get("entry", type=int) or request.args.get("entry_id", type=int)
    event_id = request.args.get("event_id", type=int)
    if entry_id and not event_id:
        erow = db.execute("SELECT event_id FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
        if erow:
            event_id = erow["event_id"]
    event_id = get_active_event_id(db, event_id)
    return render_template(
        "hyrox_tv_finisher.html",
        active_event_id=event_id,
        initial_entry_id=entry_id,
        divisions=HYROX_DIVISIONS,
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
        "signup_groups": build_signup_groups_summary(entries),
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


def _split_pair_names(display_name, partner_name=""):
    d = (display_name or "").strip()
    p = (partner_name or "").strip()
    if d and not p:
        parts = re.split(r"\s*(?:&|\+|/|\band\b|\bwith\b)\s*", d, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return parts[0].strip(), parts[1].strip()
    return d, p


def _create_entry_record(db, event_id, payload, upsert=False):
    raw_name = (payload.get("display_name") or payload.get("full_name") or "").strip()
    if not raw_name:
        first = (payload.get("first_name") or "").strip()
        last = (payload.get("last_name") or "").strip()
        raw_name = f"{first} {last}".strip()
    if not raw_name:
        return None, "Athlete name is required"

    display_name, partner_name = _split_pair_names(raw_name, payload.get("partner_name") or "")
    email = (payload.get("email") or "").strip().lower()
    dob = (payload.get("dob") or "").strip()
    age_cat = normalize_age_category(payload.get("age_category") or dob or "30-34")

    raw_div = (payload.get("division") or "").strip()
    grp_hint = (payload.get("signup_group") or "").strip()
    if not raw_div and grp_hint in HYROX_SIGNUP_GROUPS:
        raw_div = HYROX_SIGNUP_GROUPS[grp_hint]["default_division"]
    division = normalize_division(raw_div or ("mixed_doubles" if partner_name else "men_open"))
    if partner_name:
        solo_to_doubles = {
            "men_open": "men_doubles",
            "women_open": "women_doubles",
            "men_pro": "men_pro_doubles",
            "women_pro": "women_pro_doubles",
        }
        if division in solo_to_doubles:
            division = solo_to_doubles[division]

    volunteer_name = (payload.get("volunteer_name") or payload.get("volunteer") or "").strip()
    notes = (payload.get("notes") or "").strip()

    heat_id = payload.get("heat_id")
    heat_time = _normalize_heat_time_str(payload.get("heat_time") or payload.get("wave_time") or "")
    day_num = int(payload.get("day_number") or (2 if division_to_signup_group_key(division) in ("female_solo", "female_doubles") else 1))
    if heat_id:
        heat_id = int(heat_id)
    elif heat_time:
        h_row = db.execute(
            "SELECT id FROM hyrox_heats WHERE event_id=? AND COALESCE(day_number, 1)=? AND (start_time=? OR name LIKE ?) LIMIT 1",
            (event_id, day_num, heat_time, f"%{heat_time}%")
        ).fetchone()
        if not h_row and not payload.get("day_number"):
            h_row = db.execute(
                "SELECT id FROM hyrox_heats WHERE event_id=? AND (start_time=? OR name LIKE ?) LIMIT 1",
                (event_id, heat_time, f"%{heat_time}%")
            ).fetchone()
        if h_row:
            heat_id = h_row["id"]
        else:
            ev_row = db.execute("SELECT event_date, end_date FROM hyrox_events WHERE id=?", (event_id,)).fetchone()
            slot_date = ""
            if ev_row:
                slot_date = (ev_row["end_date"] if day_num == 2 and ev_row["end_date"] else ev_row["event_date"]) or ""
            existing_max = db.execute(
                "SELECT COALESCE(MAX(heat_number), 0) as m FROM hyrox_heats WHERE event_id=?",
                (event_id,)
            ).fetchone()["m"]
            h_num = existing_max + 1
            div_label = HYROX_DIVISIONS.get(division, {}).get("label", "")
            slot_name = f"Day {day_num} · {heat_time} — {div_label}" if div_label else f"Day {day_num} · Slot {h_num} — {heat_time}"
            cur_h = db.execute(
                "INSERT INTO hyrox_heats (event_id, heat_number, day_number, slot_date, division_block, name, start_time, max_lanes, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'scheduled')",
                (event_id, h_num, day_num, slot_date, division, slot_name, heat_time)
            )
            heat_id = cur_h.lastrowid
    else:
        slot_helper = {
            "display_name": display_name,
            "email": email,
            "division": division,
        }
        _assign_weekend_group_slot(db, event_id, slot_helper)
        if slot_helper.get("heat_id"):
            heat_id = int(slot_helper["heat_id"])

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
            new_notes = notes if (payload.get("replace_notes") and notes) else (existing_entry["notes"] or notes)
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


def _parse_simple_entry_line(raw_line, default_division="men_open"):
    """
    Parse a single line of simplified text entry into an entry payload dict.
    Supported flexible formats:
      - "Callum Boyd"
      - "Luke Shaw & Dan Reid"
      - "14:00 Callum Boyd"
      - "15:30 - Luke Shaw & Dan Reid"
      - "Hannah Millar, 10:20, Coach Laura"
      - "Sam Kerr & Chloe Grant | Mixed Doubles | 16:00 | Coach Chris"
    """
    line = (raw_line or "").strip()
    if not line or line.startswith("#"):
        return None

    heat_time = ""
    # Check leading HH:MM time prefix (e.g. "14:00 Callum Boyd" or "14:00 - Callum Boyd")
    m_lead = re.match(r"^(\d{1,2}:\d{2})\s*[-–—|,:]?\s*(.+)$", line)
    if m_lead:
        heat_time = _normalize_heat_time_str(m_lead.group(1))
        line = m_lead.group(2).strip()

    # Split remaining fields by "|" or "," if present
    tokens = [t.strip() for t in re.split(r"\s*[|,]\s*", line) if t.strip()]
    if not tokens:
        return None

    name_part = tokens[0]
    division = default_division
    volunteer = ""

    for extra in tokens[1:]:
        norm_t = _normalize_heat_time_str(extra)
        if re.match(r"^\d{2}:\d{2}$", norm_t) and not heat_time:
            heat_time = norm_t
            continue
        low_ex = extra.lower()
        if any(k in low_ex for k in ("open", "pro", "double", "pair", "mixed", "male", "female", "men", "women", "solo")):
            division = normalize_division(extra)
            continue
        if not volunteer:
            volunteer = extra

    display_name, partner_name = _split_pair_names(name_part, "")
    if not display_name:
        return None

    return {
        "display_name": display_name,
        "partner_name": partner_name,
        "division": division,
        "heat_time": heat_time,
        "volunteer_name": volunteer,
    }


@hyrox_bp.route("/api/hyrox/events/<int:event_id>/entries/bulk-simple", methods=["POST"])
def api_bulk_simple_entries(event_id):
    """
    Quickly add multiple athletes or doubles pairs from a plain list of lines
    (or JSON items) into the specified division / weekend sign-up group.
    """
    db = get_db()
    ensure_hyrox_tables(db)
    ev = db.execute("SELECT * FROM hyrox_events WHERE id=?", (event_id,)).fetchone()
    if not ev:
        return jsonify({"error": "Event not found"}), 404

    data = request.get_json(force=True) or {}
    group_key = (data.get("signup_group") or "").strip()
    raw_div = (data.get("division") or "").strip()
    if not raw_div and group_key in HYROX_SIGNUP_GROUPS:
        raw_div = HYROX_SIGNUP_GROUPS[group_key]["default_division"]
    default_div = normalize_division(raw_div or "men_open")
    default_vol = (data.get("volunteer_name") or "").strip()

    lines_text = data.get("lines_text") or data.get("text") or ""
    items = data.get("items")
    parsed_payloads = []

    if isinstance(items, list):
        for item in items:
            if isinstance(item, str):
                p = _parse_simple_entry_line(item, default_division=default_div)
                if p:
                    parsed_payloads.append(p)
            elif isinstance(item, dict):
                item_copy = dict(item)
                if not item_copy.get("division"):
                    item_copy["division"] = default_div
                parsed_payloads.append(item_copy)
    elif lines_text.strip():
        for raw_line in lines_text.splitlines():
            p = _parse_simple_entry_line(raw_line, default_division=default_div)
            if p:
                parsed_payloads.append(p)

    if not parsed_payloads:
        return jsonify({"error": "Enter at least one athlete or pair name"}), 400

    created_ids = []
    for p in parsed_payloads:
        if default_vol and not p.get("volunteer_name"):
            p["volunteer_name"] = default_vol
        eid, _ = _create_entry_record(db, event_id, p, upsert=False)
        if eid:
            created_ids.append(eid)

    db.commit()
    rows = db.execute("SELECT * FROM hyrox_entries WHERE event_id=? ORDER BY id ASC", (event_id,)).fetchall()
    entries = [serialize_entry(db, r, include_splits=False, include_history=False) for r in rows]
    return jsonify({
        "ok": True,
        "added_count": len(created_ids),
        "added_entry_ids": created_ids,
        "entries": entries,
        "signup_groups": build_signup_groups_summary(entries),
    }), 201


@hyrox_bp.route("/api/hyrox/events/<int:event_id>/clear-entries", methods=["POST"])
def api_clear_event_entries(event_id):
    """Remove all entries and splits for an event and reset its heats to 'scheduled'."""
    db = get_db()
    ensure_hyrox_tables(db)
    ev = db.execute("SELECT * FROM hyrox_events WHERE id=?", (event_id,)).fetchone()
    if not ev:
        return jsonify({"error": "Event not found"}), 404

    db.execute("DELETE FROM hyrox_splits WHERE entry_id IN (SELECT id FROM hyrox_entries WHERE event_id=?)", (event_id,))
    cur = db.execute("DELETE FROM hyrox_entries WHERE event_id=?", (event_id,))
    db.execute("UPDATE hyrox_heats SET status='scheduled' WHERE event_id=?", (event_id,))
    db.commit()
    return jsonify({
        "ok": True,
        "deleted_count": cur.rowcount,
    })


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


def _apply_entry_patch(db, row, data):
    entry_id = row["id"]
    new_division = normalize_division(data.get("division", row["division"]))
    is_doubles_div = bool(HYROX_DIVISIONS.get(new_division, {}).get("is_doubles"))
    new_age_cat = normalize_age_category(data.get("age_category", row["age_category"]))
    new_display_name = (data.get("display_name", row["display_name"]) or "").strip() or row["display_name"]
    if "partner_name" in data:
        new_partner_name = (data.get("partner_name") or "").strip()
    else:
        new_partner_name = (row["partner_name"] or "").strip()

    # If the Race Director edited combined 'Athlete 1 & Athlete 2' inline or switched between Doubles and Solo:
    if not is_doubles_div:
        if " & " in new_display_name:
            new_display_name = new_display_name.split(" & ", 1)[0].strip() or new_display_name
        new_partner_name = ""
    elif " & " in new_display_name and "partner_name" not in data:
        parts = [p.strip() for p in new_display_name.split(" & ", 1)]
        if parts[0]:
            new_display_name = parts[0]
            new_partner_name = parts[1] if len(parts) > 1 else ""
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
    return same_heat_volunteer_warning


@hyrox_bp.route("/api/hyrox/entries/batch-update", methods=["POST", "PUT"])
def api_entries_batch_update():
    db = get_db()
    ensure_hyrox_tables(db)
    body = request.get_json(force=True) or {}
    updates = body.get("updates") or []
    if not isinstance(updates, list):
        return jsonify({"error": "updates must be a list"}), 400

    updated_ids = []
    warnings = []
    for item in updates:
        if not isinstance(item, dict):
            continue
        eid = item.get("id") or item.get("entry_id")
        if not eid:
            continue
        row = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (int(eid),)).fetchone()
        if not row:
            continue
        warn = _apply_entry_patch(db, row, item)
        if warn:
            warnings.append(warn)
        updated_ids.append(int(eid))

    db.commit()
    return jsonify({
        "ok": True,
        "updated_count": len(updated_ids),
        "updated_ids": updated_ids,
        "warnings": warnings,
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
    same_heat_volunteer_warning = _apply_entry_patch(db, row, data)
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


def _sync_client_splits_state(db, entry_id, started_at_ms=None, splits_state=None):
    """Ensure server entry has client's started_at_ms and any completed splits from splits_state."""
    if started_at_ms:
        db.execute(
            "UPDATE hyrox_entries SET started_at_ms=COALESCE(started_at_ms, ?), "
            "status=CASE WHEN status='scheduled' THEN 'racing' ELSE status END, "
            "updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (int(started_at_ms), entry_id),
        )
    if isinstance(splits_state, list):
        for item in splits_state:
            if not isinstance(item, dict):
                continue
            s_idx = item.get("split_index")
            s_dur = item.get("duration_ms")
            s_comp = item.get("completed_at_ms")
            if s_idx is not None and s_dur is not None:
                db.execute(
                    "UPDATE hyrox_splits SET duration_ms=?, completed_at_ms=COALESCE(?, completed_at_ms), "
                    "edited_by= CASE WHEN edited_by='' THEN 'volunteer' ELSE edited_by END "
                    "WHERE entry_id=? AND split_index=?",
                    (int(s_dur), int(s_comp) if s_comp else None, entry_id, int(s_idx)),
                )


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
    explicit_action = data.get("action")
    target_split_index = data.get("split_index")

    # Sync any prior client state first so out-of-order/rapid mobile taps never lose earlier splits
    if data.get("started_at_ms") or data.get("splits_state"):
        _sync_client_splits_state(
            db,
            entry_id,
            started_at_ms=data.get("started_at_ms"),
            splits_state=data.get("splits_state"),
        )
        row = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()

    if explicit_action == "start" or (not row["started_at_ms"] and not target_split_index):
        start_val = int(data.get("started_at_ms") or now_ms)
        db.execute(
            "UPDATE hyrox_entries SET status='racing', started_at_ms=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (start_val, entry_id)
        )
        db.commit()
        updated = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()
        return jsonify({
            "ok": True,
            "action": "started",
            "server_time_ms": int(time.time() * 1000),
            "entry": serialize_entry(db, updated, include_splits=True, include_history=False),
        })

    if not row["started_at_ms"]:
        db.execute(
            "UPDATE hyrox_entries SET status='racing', started_at_ms=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (int(data.get("started_at_ms") or (now_ms - 1000)), entry_id)
        )
        row = db.execute("SELECT * FROM hyrox_entries WHERE id=?", (entry_id,)).fetchone()

    splits = db.execute(
        "SELECT * FROM hyrox_splits WHERE entry_id=? ORDER BY split_index ASC",
        (entry_id,)
    ).fetchall()

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
    data = request.get_json(silent=True) or {}
    req_undone_idx = data.get("undone_split_index")
    remaining_splits = data.get("remaining_splits")

    # If client sent its authoritative remaining splits + undone_split_index, sync prior splits first
    if data.get("started_at_ms") or isinstance(remaining_splits, list):
        _sync_client_splits_state(
            db,
            entry_id,
            started_at_ms=data.get("started_at_ms"),
            splits_state=remaining_splits,
        )

    if req_undone_idx is not None and int(req_undone_idx) >= 1:
        undone_index = int(req_undone_idx)
        db.execute(
            "UPDATE hyrox_splits SET duration_ms=NULL, completed_at_ms=NULL WHERE entry_id=? AND split_index>=?",
            (entry_id, undone_index),
        )
        db.execute(
            "UPDATE hyrox_entries SET status='racing', finished_at_ms=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (entry_id,),
        )
        recalculate_entry_totals(db, entry_id)
    else:
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

    div_info = HYROX_DIVISIONS.get(row["division"], HYROX_DIVISIONS["men_open"])
    target_reps = int(div_info["wall_ball_target_reps"])
    data = request.get_json(force=True) or {}
    current_reps = int(row["wall_ball_reps"] or 0)
    current_unbroken = bool(row["wall_ball_unbroken"]) if "wall_ball_unbroken" in row.keys() else False

    if "reps" in data:
        new_reps = max(0, int(data["reps"]))
    elif "delta" in data:
        new_reps = max(0, current_reps + int(data["delta"]))
    else:
        new_reps = current_reps

    if "unbroken" in data:
        new_unbroken = bool(data["unbroken"])
        if new_unbroken and "reps" not in data and "delta" not in data:
            new_reps = max(new_reps, target_reps)
    elif "reps" in data and int(data["reps"]) == 0:
        new_unbroken = False
    else:
        new_unbroken = current_unbroken

    db.execute(
        "UPDATE hyrox_entries SET wall_ball_reps=?, wall_ball_unbroken=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (new_reps, 1 if new_unbroken else 0, entry_id)
    )
    db.commit()
    return jsonify({
        "ok": True,
        "wall_ball_reps": new_reps,
        "wall_ball_unbroken": new_unbroken,
        "wall_ball_target_reps": target_reps,
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
            "wall_ball_unbroken=0, updated_at=CURRENT_TIMESTAMP WHERE id=?",
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

    # Division inference from custom field, TeamUp event name (prioritized over shared offering_type name),
    # booking notes, Saturday (Group 1 Male Solo / Group 2 Male & Mixed Doubles) vs Sunday (Group 3 Female Solo / Group 4 Female Doubles),
    # or gender fallback.
    explicit_div = (
        att_obj.get("division")
        or custom_fields.get("division")
        or custom_fields.get("hyrox_division")
        or custom_fields.get("category")
        or ""
    ).strip()
    event_name = (
        event_obj.get("name")
        or att_obj.get("event_name")
        or ""
    ).strip()
    offering_name = (
        offering_obj.get("name")
        or att_obj.get("offering_type_name")
        or ""
    ).strip()
    # Prioritize event.name (e.g. 'Hyrox simulation solo', 'Hyrox simulation doubles male and mixed doubles',
    # 'Hyrox simulations female open solo', 'Hyrox simulations female open doubles') over offering_type.name,
    # because TeamUp reuses a combined offering_type ('Hyrox simulation solo males ,solo woman pro & female pro double')
    event_or_offering_name = event_name or offering_name
    booking_notes_str = str(att_obj.get("notes") or att_obj.get("booking_notes") or "").strip()

    # Wave / Heat time & weekday from event local_starts_at / starts_at or explicit heat_time
    raw_starts = (
        att_obj.get("heat_time")
        or event_obj.get("local_starts_at")
        or event_obj.get("starts_at")
        or att_obj.get("event_starts_at")
        or event_obj.get("name")
        or ""
    )
    heat_time = _normalize_heat_time_str(raw_starts)

    # Detect Saturday (Day 1, 14:00-17:00) vs Sunday (Day 2, 10:00-14:00) from event date or title
    primary_title_low = event_or_offering_name.lower()
    combined_title_low = f"{event_or_offering_name} {booking_notes_str}".lower()
    is_sunday_event = ("sunday" in combined_title_low or "sun " in combined_title_low)
    is_saturday_event = ("saturday" in combined_title_low or "sat " in combined_title_low)
    m_date = re.search(r"(\d{4}-\d{2}-\d{2})", str(raw_starts))
    if m_date:
        try:
            ev_dt = datetime.strptime(m_date.group(1), "%Y-%m-%d").date()
            if ev_dt.weekday() == 6:
                is_sunday_event = True
            elif ev_dt.weekday() == 5:
                is_saturday_event = True
        except Exception:
            pass

    div_keywords = (
        "open", "pro", "double", "doubles", "pair", "pairs", "solo", "sole", "single",
        "mixed", "women", "womens", "female", "females", "ladies", "men", "mens", "male", "males",
    )
    is_female_gender = gender_raw in ("f", "female", "woman", "women", "w")
    ev_tokens = set(re.sub(r"[^a-z0-9]+", " ", primary_title_low).split())
    is_doubles_event = bool(ev_tokens & {"double", "doubles", "pair", "pairs", "dbl"}) or ("double" in primary_title_low or "pair" in primary_title_low) or bool(partner_name)
    is_pro_event = bool(ev_tokens & {"pro", "pros"})
    has_female_in_event = bool(ev_tokens & {"female", "females", "women", "womens", "woman", "ladies"})
    has_male_in_event = bool(ev_tokens & {"male", "males", "men", "mens", "man"}) and not has_female_in_event

    has_explicit_division = True
    if explicit_div:
        div_resolved = normalize_division(explicit_div)
    elif booking_notes_str and any(k in booking_notes_str.lower() for k in div_keywords):
        div_resolved = normalize_division(booking_notes_str)
    elif is_sunday_event and not has_male_in_event:
        # Sunday (10:00-14:00) has 2 options:
        #   - Group 3: Female Solo ('Hyrox simulations female open solo' / Sunday 'Hyrox simulation solo')
        #   - Group 4: Female Doubles ('Hyrox simulations female open doubles' / Sunday 'Hyrox simulation doubles')
        if is_doubles_event:
            div_resolved = "women_pro_doubles" if is_pro_event else "women_doubles"
        else:
            div_resolved = "women_pro" if is_pro_event else "women_open"
    elif is_saturday_event and not has_female_in_event:
        # Saturday (14:00-17:00) has 2 options:
        #   - Group 1: Male Solo ('Hyrox simulation solo')
        #   - Group 2: Male Doubles / Mixed Doubles ('Hyrox simulation doubles male and mixed doubles' / 'Hyrox simulation doubles')
        if is_doubles_event:
            if is_female_gender or "mixed" in booking_notes_str.lower() or ("mixed" in ev_tokens and not has_male_in_event):
                div_resolved = "mixed_doubles"
            else:
                div_resolved = "men_pro_doubles" if is_pro_event else "men_doubles"
        else:
            div_resolved = "men_pro" if is_pro_event else "men_open"
    elif event_or_offering_name and any(k in primary_title_low for k in div_keywords):
        div_resolved = normalize_division(event_or_offering_name)
        if is_doubles_event and ("mixed" in primary_title_low and has_male_in_event):
            div_resolved = "mixed_doubles" if is_female_gender else "men_doubles"
    elif partner_name:
        div_resolved = "women_doubles" if is_female_gender else "mixed_doubles"
    else:
        div_resolved = default_open_div
        has_explicit_division = False

    signup_group = division_to_signup_group_key(div_resolved)
    group_meta = HYROX_SIGNUP_GROUPS[signup_group]
    day_number = group_meta["day_number"]

    # Instructor / Volunteer fallback if event has instructors expanded
    volunteer = (att_obj.get("volunteer_name") or "").strip()
    instructors = event_obj.get("instructors")
    if not volunteer and isinstance(instructors, list) and instructors:
        first_inst = instructors[0]
        if isinstance(first_inst, dict):
            volunteer = (first_inst.get("name") or "").strip()

    att_status = str(att_obj.get("status") or "registered").strip().lower()
    notes_parts = []
    if event_or_offering_name:
        notes_parts.append(event_or_offering_name)
    if att_obj.get("id"):
        notes_parts.append(f"TeamUp Attendance #{att_obj['id']}")
    if event_obj.get("id"):
        notes_parts.append(f"TeamUp Event #{event_obj['id']}")
    if att_obj.get("notes"):
        notes_parts.append(str(att_obj["notes"]).strip())

    result = {
        "display_name": full_name,
        "partner_name": partner_name,
        "email": email,
        "dob": str(dob).strip(),
        "age_category": normalize_age_category(age_cat_raw),
        "division": div_resolved,
        "division_label": HYROX_DIVISIONS.get(div_resolved, {}).get("label", div_resolved),
        "signup_group": signup_group,
        "signup_group_label": group_meta["label"],
        "day_number": day_number,
        "has_explicit_division": has_explicit_division,
        "has_explicit_age": bool(age_cat_raw or dob),
        "heat_time": heat_time,
        "event_starts_at": str(raw_starts),
        "teamup_event_name": event_or_offering_name,
        "volunteer_name": volunteer,
        "teamup_customer_id": str(customer_id).strip(),
        "teamup_attendance_status": att_status,
        "notes": " · ".join(notes_parts),
    }
    return enrich_entry_from_road_to_glasgow(result)


# Confirmed 13 Saturday 28th & Sunday 29th HYROX Simulation sign-ups cross-referenced
# with the CS Performance "Road to Glasgow" spreadsheet.
CONFIRMED_SAT28_SUN29_SIGNUPS = [
    # Group 1 — 1. Male Solo (Saturday 28th, 14:00–17:00)
    {
        "order": 1,
        "display_name": "Lucas Kane",
        "aliases": ["lucas kane", "lucas"],
        "partner_name": "",
        "division": "men_open",
        "volunteer_name": "Danielle",
        "day_number": 1,
        "slot_time": "14:00",
        "teamup_event_name": "Hyrox simulation solo",
        "road_to_glasgow_note": "Confirmed Men's Solo Open (Road to Glasgow)",
    },
    {
        "order": 2,
        "display_name": "Ross Martin",
        "aliases": ["ross martin", "riss martin", "riss marting"],
        "partner_name": "",
        "division": "men_open",
        "volunteer_name": "Connie",
        "day_number": 1,
        "slot_time": "14:00",
        "teamup_event_name": "Hyrox simulation solo",
        "road_to_glasgow_note": "Confirmed Men's Solo Open (Road to Glasgow)",
    },
    {
        "order": 3,
        "display_name": "Scott Firth",
        "aliases": ["scott firth"],
        "partner_name": "",
        "division": "men_open",
        "volunteer_name": "Hannah",
        "day_number": 1,
        "slot_time": "14:00",
        "teamup_event_name": "Hyrox simulation solo",
        "road_to_glasgow_note": "Confirmed Men's Solo Open (Road to Glasgow)",
    },
    # Group 2 — 2. Male Doubles / Mixed Doubles (Saturday 28th, 14:00–17:00)
    {
        "order": 4,
        "display_name": "Eilidh Mcmanus",
        "aliases": ["eilidh mcmanus", "eilidh"],
        "partner_name": "Jax Stevenson",
        "division": "mixed_doubles",
        "volunteer_name": "Joely",
        "day_number": 1,
        "slot_time": "14:20",
        "teamup_event_name": "Hyrox simulation doubles male and mixed doubles",
        "road_to_glasgow_note": "Confirmed Mixed Doubles Open w/ Jax Stevenson (Road to Glasgow)",
    },
    {
        "order": 5,
        "display_name": "Ewan Stewart",
        "aliases": ["ewan stewart"],
        "partner_name": "Ewan Taylor",
        "division": "men_doubles",
        "volunteer_name": "Ross Crombie",
        "day_number": 1,
        "slot_time": "14:45",
        "teamup_event_name": "Hyrox simulation doubles male and mixed doubles",
        "road_to_glasgow_note": "Confirmed Male Doubles Open w/ Ewan Taylor (Road to Glasgow)",
    },
    {
        "order": 6,
        "display_name": "Keiran Jackson",
        "aliases": ["keiran jackson", "kieran jackson"],
        "partner_name": "Ricky Simpson",
        "division": "men_doubles",
        "volunteer_name": "Katie Sharkey",
        "day_number": 1,
        "slot_time": "14:25",
        "teamup_event_name": "Hyrox simulation doubles male and mixed doubles",
        "road_to_glasgow_note": "Confirmed Male Doubles Open w/ Ricky Simpson (Road to Glasgow)",
    },
    {
        "order": 7,
        "display_name": "Scott McDonald",
        "aliases": ["scott mcdonald"],
        "partner_name": "Liam Blair",
        "division": "men_doubles",
        "volunteer_name": "Robert Myler",
        "day_number": 1,
        "slot_time": "14:30",
        "teamup_event_name": "Hyrox simulation doubles male and mixed doubles",
        "road_to_glasgow_note": "Confirmed Male Doubles Open w/ Liam Blair (Road to Glasgow)",
    },
    {
        "order": 8,
        "display_name": "Steven Rosie",
        "aliases": ["steven rosie"],
        "partner_name": "Fiona Sharp",
        "division": "mixed_doubles",
        "volunteer_name": "Allen Gibson",
        "day_number": 1,
        "slot_time": "14:35",
        "teamup_event_name": "Hyrox simulation doubles male and mixed doubles",
        "road_to_glasgow_note": "Confirmed Mixed Doubles Open w/ Fiona Sharp (Road to Glasgow)",
    },
    {
        "order": 9,
        "display_name": "Joe Wardle",
        "aliases": ["joe wardle"],
        "partner_name": "",
        "division": "men_open",
        "volunteer_name": "Jamie",
        "day_number": 1,
        "slot_time": "14:40",
        "teamup_event_name": "Hyrox simulation solo",
        "road_to_glasgow_note": "Confirmed Men's Solo Open (Road to Glasgow)",
    },
    # Group 3 — 3. Female Solo (Sunday 29th, 10:00–14:00)
    {
        "order": 10,
        "display_name": "Eve Cunningham",
        "aliases": ["eve cunningham"],
        "partner_name": "",
        "division": "women_open",
        "volunteer_name": "Sheryl",
        "day_number": 2,
        "slot_time": "10:00",
        "teamup_event_name": "Hyrox simulations female open solo",
        "road_to_glasgow_note": "Confirmed Female Solo Open (Road to Glasgow)",
    },
    {
        "order": 11,
        "display_name": "Joanne Campbell",
        "aliases": ["joanne campbell"],
        "partner_name": "",
        "division": "women_open",
        "volunteer_name": "Eilidh",
        "day_number": 2,
        "slot_time": "10:05",
        "teamup_event_name": "Hyrox simulations female open solo",
        "road_to_glasgow_note": "Confirmed Female Solo Open (Road to Glasgow)",
    },
    {
        "order": 12,
        "display_name": "Lesley Anne Cooper",
        "aliases": ["lesley anne cooper", "lesley ann cooper"],
        "partner_name": "",
        "division": "women_open",
        "volunteer_name": "Scott McDonald",
        "day_number": 2,
        "slot_time": "10:10",
        "teamup_event_name": "Hyrox simulations female open solo",
        "road_to_glasgow_note": "Confirmed Female Solo Open (Road to Glasgow)",
    },
    {
        "order": 13,
        "display_name": "Ava Stewart",
        "aliases": ["ava stewart"],
        "partner_name": "",
        "division": "women_open",
        "volunteer_name": "Allen Gibson",
        "day_number": 2,
        "slot_time": "10:15",
        "teamup_event_name": "Hyrox simulations female open solo",
        "road_to_glasgow_note": "Confirmed Female Solo Open (Road to Glasgow)",
    },
]

CONFIRMED_ADDITIONAL_SCREENSHOT_SIGNUPS = [
    # Group 4 — 4. Female Doubles (Sunday 29th, 10:00–14:00)
    {
        "order": 14,
        "display_name": "Louise Menealy",
        "aliases": ["louise menealy", "louise mcnealy"],
        "partner_name": "Louise",
        "division": "women_doubles",
        "volunteer_name": "Jamie",
        "day_number": 2,
        "slot_time": "10:20",
        "teamup_event_name": "Hyrox simulations female open doubles",
        "road_to_glasgow_note": "Confirmed Female Doubles Open",
    },
]

# Additional Doubles pairs from Road to Glasgow.xlsx so any future TeamUp Doubles
# booking automatically fills in their partner and division.
ROAD_TO_GLASGOW_DOUBLES_DIRECTORY = {
    "martin kerr": {"partner_name": "Danny Frame", "division": "men_doubles"},
    "danny frame": {"partner_name": "Martin Kerr", "division": "men_doubles"},
    "james brown": {"partner_name": "Lauren Brown", "division": "mixed_doubles"},
    "lauren brown": {"partner_name": "James Brown", "division": "mixed_doubles"},
    "gary morris": {"partner_name": "Kelly Morris", "division": "mixed_doubles"},
    "kelly morris": {"partner_name": "Gary Morris", "division": "mixed_doubles"},
    "craig burns": {"partner_name": "Victoria Burns", "division": "mixed_doubles"},
    "victoria burns": {"partner_name": "Craig Burns", "division": "mixed_doubles"},
    "callum hair": {"partner_name": "Nicoletta Contuzzi", "division": "mixed_doubles"},
    "nicoletta contuzzi": {"partner_name": "Callum Hair", "division": "mixed_doubles"},
    "lauren goldie": {"partner_name": "Kirsty Campbell", "division": "women_doubles"},
    "kirsty campbell": {"partner_name": "Lauren Goldie", "division": "women_doubles"},
    "heather whyte": {"partner_name": "Kirstin Leighton", "division": "women_doubles"},
    "kirstin leighton": {"partner_name": "Heather Whyte", "division": "women_doubles"},
    "kirsten borthwick": {"partner_name": "Karen McDonald", "division": "women_doubles"},
    "karen mcdonald": {"partner_name": "Kirsten Borthwick", "division": "women_doubles"},
    "stacey maxwell": {"partner_name": "Jennifer Scobie", "division": "women_doubles"},
    "jennifer scobie": {"partner_name": "Stacey Maxwell", "division": "women_doubles"},
    "stacey adamson": {"partner_name": "Amy Borthwick", "division": "women_doubles"},
    "amy borthwick": {"partner_name": "Stacey Adamson", "division": "women_doubles"},
    "charlene frame": {"partner_name": "Rebecca Wilson", "division": "women_doubles"},
    "rebecca wilson": {"partner_name": "Charlene Frame", "division": "women_doubles"},
    "carol anne wood": {"partner_name": "Lisa Marie", "division": "women_doubles"},
    "lisa marie": {"partner_name": "Carol Anne Wood", "division": "women_doubles"},
    "kellyanne mccrae": {"partner_name": "Ashleigh Muir", "division": "women_doubles"},
    "ashleigh muir": {"partner_name": "Kellyanne McCrae", "division": "women_doubles"},
    "rachel speedie": {"partner_name": "Megan McCreadie", "division": "women_doubles"},
    "megan mccreadie": {"partner_name": "Rachel Speedie", "division": "women_doubles"},
    "amy campbell": {"partner_name": "Leighann Campbell", "division": "women_doubles"},
    "leighann campbell": {"partner_name": "Amy Campbell", "division": "women_doubles"},
    "aimee mcdonald": {"partner_name": "Chloe Smith", "division": "women_doubles"},
    "chloe smith": {"partner_name": "Aimee McDonald", "division": "women_doubles"},
    "laura mcculloch": {"partner_name": "Nicola Smith", "division": "women_doubles"},
    "nicola smith": {"partner_name": "Laura McCulloch", "division": "women_doubles"},
}


def _find_confirmed_road_to_glasgow_spec(display_name):
    norm = re.sub(r"\s+", " ", (display_name or "").strip().lower())
    if not norm:
        return None
    for item in CONFIRMED_SAT28_SUN29_SIGNUPS:
        if norm == item["display_name"].lower() or norm in item.get("aliases", []):
            return item
    return None


def enrich_entry_from_road_to_glasgow(entry_dict):
    """
    Enrich a mapped TeamUp/HYROX entry dictionary with confirmed partner names,
    divisions, and notes from the CS Performance 'Road to Glasgow' sheet.
    """
    if not isinstance(entry_dict, dict):
        return entry_dict
    name_raw = (entry_dict.get("display_name") or "").strip()
    norm = re.sub(r"\s+", " ", name_raw.lower())
    if not norm:
        return entry_dict

    spec = _find_confirmed_road_to_glasgow_spec(name_raw)
    if spec:
        div = spec["division"]
        signup_group = division_to_signup_group_key(div)
        group_meta = HYROX_SIGNUP_GROUPS[signup_group]
        if not entry_dict.get("partner_name"):
            entry_dict["partner_name"] = spec["partner_name"]
        entry_dict["division"] = div
        entry_dict["division_label"] = HYROX_DIVISIONS.get(div, {}).get("label", div)
        entry_dict["signup_group"] = signup_group
        entry_dict["signup_group_label"] = group_meta["label"]
        entry_dict["day_number"] = group_meta["day_number"]
        entry_dict["has_explicit_division"] = True
        entry_dict["replace_notes"] = True
        return entry_dict

    # Check additional Doubles pairs from Road to Glasgow if the entry was booked in a Doubles division
    cur_div = entry_dict.get("division") or ""
    if cur_div in ("men_doubles", "mixed_doubles", "women_doubles") and norm in ROAD_TO_GLASGOW_DOUBLES_DIRECTORY:
        pair_info = ROAD_TO_GLASGOW_DOUBLES_DIRECTORY[norm]
        div = pair_info["division"]
        signup_group = division_to_signup_group_key(div)
        group_meta = HYROX_SIGNUP_GROUPS[signup_group]
        if not entry_dict.get("partner_name"):
            entry_dict["partner_name"] = pair_info["partner_name"]
        entry_dict["division"] = div
        entry_dict["division_label"] = HYROX_DIVISIONS.get(div, {}).get("label", div)
        entry_dict["signup_group"] = signup_group
        entry_dict["signup_group_label"] = group_meta["label"]
        entry_dict["day_number"] = group_meta["day_number"]
        entry_dict["has_explicit_division"] = True
    return entry_dict


def _resolve_or_create_weekend_slot(db, event_id, day_number, slot_time, division="men_open"):
    slot_time = _normalize_heat_time_str(slot_time)
    day_number = int(day_number or 1)
    if not slot_time:
        return None
    existing = db.execute(
        "SELECT id FROM hyrox_heats WHERE event_id=? AND COALESCE(day_number, 1)=? AND start_time=? LIMIT 1",
        (event_id, day_number, slot_time),
    ).fetchone()
    if existing:
        return int(existing["id"])
    ev_row = db.execute("SELECT event_date, end_date FROM hyrox_events WHERE id=?", (event_id,)).fetchone()
    ev_d = dict(ev_row) if ev_row else {}
    slot_date = (ev_d.get("end_date") if day_number == 2 else ev_d.get("event_date")) or ("2026-11-29" if day_number == 2 else "2026-11-28")
    max_h = db.execute(
        "SELECT COALESCE(MAX(heat_number), 0) as m FROM hyrox_heats WHERE event_id=?",
        (event_id,),
    ).fetchone()["m"]
    h_num = int(max_h or 0) + 1
    grp_key = division_to_signup_group_key(division)
    grp_label = HYROX_SIGNUP_GROUPS.get(grp_key, {}).get("short_label", "Slot")
    h_name = f"Day {day_number} · {slot_time} — {grp_label}"
    cur_h = db.execute(
        "INSERT INTO hyrox_heats (event_id, heat_number, day_number, slot_date, division_block, transition_buffer_mins, name, start_time, max_lanes, status) "
        "VALUES (?, ?, ?, ?, ?, 0, ?, ?, 1, 'scheduled')",
        (event_id, h_num, day_number, slot_date, division, h_name, slot_time),
    )
    return int(cur_h.lastrowid)


def _apply_road_to_glasgow_enrichment_to_db(db, event_id=None):
    """
    Update any existing entries in `hyrox_entries` that match the confirmed Road to Glasgow
    roster so their partner_name, partner_athlete_id, division, volunteer_name, notes, and
    heat slot are accurate.
    """
    sql = "SELECT * FROM hyrox_entries"
    params = []
    if event_id is not None:
        sql += " WHERE event_id=?"
        params.append(event_id)
    sql += " ORDER BY id ASC"
    rows = db.execute(sql, params).fetchall()
    updated = 0
    for r in rows:
        spec = _find_confirmed_road_to_glasgow_spec(r["display_name"])
        if not spec:
            continue
        target_div = spec["division"]
        target_partner = spec["partner_name"]
        target_vol = (r["volunteer_name"] or "").strip() or (spec.get("volunteer_name") or "").strip()
        cur_notes = (r["notes"] or "").strip()
        if "road to glasgow" in cur_notes.lower() or "tbc — confirm" in cur_notes.lower():
            new_notes = cur_notes.split("·")[0].strip() if "teamup #" in cur_notes.lower() else ""
        else:
            new_notes = cur_notes

        needs_update = (
            (r["division"] or "") != target_div
            or (r["partner_name"] or "") != target_partner
            or (r["volunteer_name"] or "").strip() != target_vol
            or new_notes != cur_notes
        )
        new_heat_id = r["heat_id"]
        if spec.get("slot_time") and spec.get("day_number"):
            resolved_hid = _resolve_or_create_weekend_slot(
                db, r["event_id"], spec["day_number"], spec["slot_time"], target_div
            )
            if resolved_hid and new_heat_id != resolved_hid:
                new_heat_id = resolved_hid
                needs_update = True
        elif not new_heat_id:
            slot_helper = {
                "display_name": r["display_name"],
                "email": r["email"] or "",
                "division": target_div,
            }
            _assign_weekend_group_slot(db, r["event_id"], slot_helper)
            if slot_helper.get("heat_id"):
                new_heat_id = int(slot_helper["heat_id"])
                needs_update = True

        if needs_update:
            partner_aid = (
                find_or_create_athlete(db, full_name=target_partner, age_category=r["age_category"] or "30-34")
                if target_partner and not target_partner.startswith("TBC")
                else None
            )
            db.execute(
                "UPDATE hyrox_entries SET division=?, partner_name=?, partner_athlete_id=?, volunteer_name=?, heat_id=?, notes=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (target_div, target_partner, partner_aid, target_vol, new_heat_id, new_notes, r["id"]),
            )
            updated += 1
    return updated


def _seed_confirmed_sat28_sun29_signups(db, event_id=None, include_additional=False):
    """
    Ensure all confirmed Saturday 28th & Sunday 29th HYROX Simulation sign-ups
    (cross-referenced with Road to Glasgow + screenshot volunteers & start times)
    are present in the active weekend event.
    """
    if event_id is None:
        ev = db.execute(
            "SELECT id FROM hyrox_events ORDER BY event_date DESC, id DESC LIMIT 1"
        ).fetchone()
        if not ev:
            return 0
        event_id = ev["id"]

    roster = list(CONFIRMED_SAT28_SUN29_SIGNUPS)
    if include_additional:
        roster.extend(CONFIRMED_ADDITIONAL_SCREENSHOT_SIGNUPS)

    count = 0
    for spec in roster:
        target_hid = None
        if spec.get("slot_time") and spec.get("day_number"):
            target_hid = _resolve_or_create_weekend_slot(
                db, event_id, spec["day_number"], spec["slot_time"], spec["division"]
            )
        payload = {
            "display_name": spec["display_name"],
            "partner_name": spec["partner_name"],
            "division": spec["division"],
            "volunteer_name": spec.get("volunteer_name") or "",
            "heat_id": target_hid,
            "force_heat_time": bool(target_hid),
            "has_explicit_division": True,
            "notes": "",
            "replace_notes": True,
        }
        if not target_hid:
            _assign_weekend_group_slot(db, event_id, payload)
        eid, _ = _create_entry_record(db, event_id, payload, upsert=True)
        if eid:
            # Ensure volunteer_name and heat_id match the confirmed spec
            if spec.get("volunteer_name") or target_hid:
                db.execute(
                    "UPDATE hyrox_entries SET volunteer_name=COALESCE(NULLIF(volunteer_name, ''), ?), "
                    "heat_id=COALESCE(?, heat_id), division=?, partner_name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (
                        spec.get("volunteer_name") or "",
                        target_hid,
                        spec["division"],
                        spec["partner_name"],
                        eid,
                    ),
                )
            count += 1
    _apply_road_to_glasgow_enrichment_to_db(db, event_id=event_id)
    return count


def _restore_screenshot_volunteers_and_slots(db, event_id=None):
    """
    One-time restore of all 14 entries, start times, categories, and volunteer names
    from the Race Director's confirmed screenshot (with Joe Wardle updated to Men's Open Solo).
    """
    if event_id is None:
        ev = db.execute(
            "SELECT id FROM hyrox_events ORDER BY event_date DESC, id DESC LIMIT 1"
        ).fetchone()
        if not ev:
            return 0
        event_id = ev["id"]
    return _seed_confirmed_sat28_sun29_signups(db, event_id=event_id, include_additional=True)


@hyrox_bp.route("/api/hyrox/events/<int:event_id>/apply-road-to-glasgow", methods=["POST"])
def api_apply_road_to_glasgow(event_id):
    """
    Seed/upsert and enrich the confirmed Saturday 28th & Sunday 29th HYROX Sim
    sign-ups from the CS Performance 'Road to Glasgow' sheet into the specified event.
    """
    db = get_db()
    ensure_hyrox_tables(db)
    ev = db.execute("SELECT * FROM hyrox_events WHERE id=?", (event_id,)).fetchone()
    if not ev:
        return jsonify({"error": "HYROX Event not found"}), 404
    body = request.get_json(silent=True) or {}
    include_additional = bool(body.get("include_additional", False))
    seeded_count = _seed_confirmed_sat28_sun29_signups(
        db, event_id=event_id, include_additional=include_additional
    )
    db.commit()
    entry_rows = db.execute("SELECT * FROM hyrox_entries WHERE event_id=? ORDER BY id ASC", (event_id,)).fetchall()
    entries_final = [serialize_entry(db, r, include_splits=False, include_history=False) for r in entry_rows]
    return jsonify({
        "ok": True,
        "seeded_count": seeded_count,
        "entries": entries_final,
        "signup_groups": build_signup_groups_summary(entries_final),
    })


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


def get_next_weekend_dates(ref_date=None):
    """Return (saturday_iso, sunday_iso) defaulting to Saturday 28th & Sunday 29th (2026-11-28 / 2026-11-29)."""
    if ref_date is None:
        return "2026-11-28", "2026-11-29"
    from datetime import timedelta
    d = ref_date
    days_ahead = (5 - d.weekday()) % 7
    sat = d + timedelta(days=days_ahead)
    sun = sat + timedelta(days=1)
    return sat.isoformat(), sun.isoformat()


def _is_weekend_hyrox_sim_attendance(att_obj):
    """
    Filter TeamUp attendances so regular morning gym classes (e.g. 05:30 Thresholds,
    07:00 Strength & conditioning, 09:30 Hot Strength & Ergs [30 attendees],
    10:45 Hyrox Youngstars age 8-16 [2 attendees], 12:45 NXTGen little legends,
    and Sunday 07:00 Hyrox Specific Training) are excluded when pulling
    Saturday (14:00-17:00) & Sunday (10:00-14:00) HYROX Simulation sign-ups.
    """
    if not isinstance(att_obj, dict):
        return False
    event_obj = att_obj.get("event") if isinstance(att_obj.get("event"), dict) else {}
    offering_obj = event_obj.get("offering_type") if isinstance(event_obj.get("offering_type"), dict) else {}
    title = " ".join([
        str(event_obj.get("name") or ""),
        str(offering_obj.get("name") or ""),
        str(att_obj.get("event_name") or ""),
        str(att_obj.get("offering_type_name") or ""),
    ]).strip().lower()

    # Exclude kids classes and non-HYROX regular gym classes
    excluded_phrases = (
        "youngstars", "little legends", "nxtgen", "age 8-16", "age 5-7",
        "thresholds", "hot strength", "strength & conditioning", "specific training",
    )
    if any(p in title for p in excluded_phrases):
        return False

    # If a class title is present, require that it is a HYROX simulation / division event
    if title:
        has_sim_or_hyrox = ("sim" in title or "hyrox" in title)
        if not has_sim_or_hyrox:
            return False

    return True


def _fetch_weekend_teamup_signups(client, sat_date, sun_date, query=None, event_ids=None, status="registered"):
    """
    Query TeamUp API v2 for Saturday (`sat_date`) & Sunday (`sun_date`) sign-ups.
    If 0 HYROX sign-ups are found on the primary dates and `event_ids` is not pinned,
    also check candidate 28th/29th weekend windows in 2026 so Saturday 28th & Sunday 29th
    sign-ups are discovered regardless of month.
    """
    candidate_windows = [(sat_date, sun_date)]
    for cand_sat, cand_sun in [
        ("2026-11-28", "2026-11-29"),
        ("2026-03-28", "2026-03-29"),
        ("2026-04-28", "2026-04-29"),
        ("2026-04-25", "2026-04-26"),
        ("2026-05-30", "2026-05-31"),
    ]:
        if (cand_sat, cand_sun) not in candidate_windows:
            candidate_windows.append((cand_sat, cand_sun))

    if event_ids:
        candidate_windows = [(sat_date, sun_date)]

    chosen_sat, chosen_sun = sat_date, sun_date
    chosen_events = []
    chosen_attendances = []

    for idx, (c_sat, c_sun) in enumerate(candidate_windows):
        starts_gte = f"{c_sat}T00:00:00Z" if len(c_sat) == 10 else c_sat
        starts_lte = f"{c_sun}T23:59:59Z" if len(c_sun) == 10 else c_sun
        evs = client.list_events(starts_at_gte=starts_gte, starts_at_lte=starts_lte, query=query)
        atts = client.list_attendances(
            event_ids=event_ids,
            starts_at_gte=starts_gte,
            starts_at_lte=starts_lte,
            status=status,
        )
        filtered_atts = [a for a in (atts or []) if _is_weekend_hyrox_sim_attendance(a)]
        if idx == 0:
            chosen_events = evs
            chosen_attendances = filtered_atts
        if filtered_atts:
            return c_sat, c_sun, evs, filtered_atts

    return chosen_sat, chosen_sun, chosen_events, chosen_attendances


def _hm_to_mins(hm_str, default_mins=840):
    m = re.match(r"^(\d{1,2}):(\d{2})$", str(hm_str or "").strip())
    if not m:
        return default_mins
    return int(m.group(1)) * 60 + int(m.group(2))


def _mins_to_hm(total_mins):
    return f"{(int(total_mins) // 60) % 24:02d}:{int(total_mins) % 60:02d}"


def _assign_weekend_group_slot(db, event_id, mapped, interval_mins=5):
    """
    Assign a 1:1 heat slot within the entry's 4-group weekend window:
      - Group 1 (male_solo):           Day 1 (Sat) 14:00 - 15:20
      - Group 2 (male_mixed_doubles):  Day 1 (Sat) 15:30 - 17:00
      - Group 3 (female_solo):         Day 2 (Sun) 10:00 - 11:50
      - Group 4 (female_doubles):      Day 2 (Sun) 12:00 - 14:00
    If the athlete already has an entry in `event_id` with a `heat_id`, keep it.
    Otherwise, pick the earliest unoccupied 1:1 heat in that group's day & time window
    (or create the next staggered slot at `interval_mins`).
    """
    div_key = normalize_division(mapped.get("division") or "men_open")
    grp_key = division_to_signup_group_key(div_key)
    grp_meta = HYROX_SIGNUP_GROUPS[grp_key]
    day_num = grp_meta["day_number"]
    mapped["day_number"] = day_num

    start_floor_mins = _hm_to_mins(grp_meta["default_start_time"], 14 * 60 if day_num == 1 else 10 * 60)
    end_ceil_mins = _hm_to_mins(grp_meta["default_end_time"], 17 * 60 if day_num == 1 else 14 * 60)

    display_name = (mapped.get("display_name") or "").strip()
    email = (mapped.get("email") or "").strip().lower()
    if display_name:
        existing = db.execute(
            "SELECT id, heat_id, division, partner_name FROM hyrox_entries WHERE event_id=? AND ("
            "(? != '' AND LOWER(email)=?) OR LOWER(display_name)=?) LIMIT 1",
            (event_id, email, email, display_name.lower()),
        ).fetchone()
        if existing and existing["heat_id"]:
            # If the Race Director manually added a partner, preserve their custom slot/division
            if existing["partner_name"] and not mapped.get("partner_name"):
                mapped["heat_id"] = existing["heat_id"]
                return
            # Check if existing heat is already on the right day & within this group's time window
            cur_heat = db.execute("SELECT day_number, start_time FROM hyrox_heats WHERE id=?", (existing["heat_id"],)).fetchone()
            if cur_heat:
                cur_hm = _hm_to_mins(cur_heat["start_time"], -1)
                preserve_floor = min(start_floor_mins, 9 * 60 + 30) if day_num == 2 else start_floor_mins
                if int(cur_heat["day_number"] or 1) == day_num and preserve_floor <= cur_hm <= end_ceil_mins:
                    mapped["heat_id"] = existing["heat_id"]
                    return
            # Otherwise, the entry was previously in the wrong group/day window — move it to this group's slot
            mapped["force_heat_time"] = True
            mapped["replace_notes"] = True

    heats = db.execute(
        "SELECT h.*, (SELECT COUNT(*) FROM hyrox_entries e WHERE e.heat_id=h.id AND e.status != 'dns') as used_lanes "
        "FROM hyrox_heats h WHERE h.event_id=? AND COALESCE(h.day_number, 1)=? "
        "ORDER BY h.start_time ASC, h.heat_number ASC",
        (event_id, day_num),
    ).fetchall()

    # 1. Check for an open slot inside this group's time window [start_floor_mins, end_ceil_mins]
    group_heats = []
    for h in heats:
        hm = _hm_to_mins(h["start_time"], -1)
        if start_floor_mins <= hm <= end_ceil_mins:
            group_heats.append((hm, h))
            max_l = int(h["max_lanes"] or 1)
            if int(h["used_lanes"] or 0) < max_l:
                mapped["heat_id"] = h["id"]
                mapped["heat_time"] = h["start_time"]
                return

    # 2. Otherwise create the next staggered slot in this group's block
    if group_heats:
        last_mins = group_heats[-1][0]
        next_mins = last_mins + max(int(interval_mins or 5), 1)
    else:
        next_mins = start_floor_mins
    mapped["heat_time"] = _mins_to_hm(next_mins)


@hyrox_bp.route("/api/hyrox/teamup/signups", methods=["GET", "POST"])
def api_teamup_signups_preview():
    """
    Fetch or parse TeamUp sign-ups and return them organized into the 4 weekend groups:
      1. Male Solo (Sat 14:00-17:00)
      2. Male Doubles / Mixed Doubles (Sat 14:00-17:00)
      3. Female Solo (Sun 10:00-14:00)
      4. Female Doubles (Sun 10:00-14:00)
    """
    db = get_db()
    ensure_hyrox_tables(db)
    data = (request.get_json(silent=True) or {}) if request.method == "POST" else {}
    args = request.args

    sat_default, sun_default = get_next_weekend_dates()
    sat_date = (data.get("saturday_date") or args.get("saturday_date") or sat_default).strip()
    sun_date = (data.get("sunday_date") or args.get("sunday_date") or sun_default).strip()

    attendances = data.get("attendances")
    if isinstance(data.get("results"), list) and attendances is None:
        attendances = data["results"]

    remote_events = []
    teamup_configured = False
    if attendances is None:
        cfg = get_teamup_config(db)
        teamup_configured = cfg["configured"]
        if not cfg["has_token"]:
            return jsonify({
                "ok": False,
                "configured": False,
                "saturday_date": sat_date,
                "sunday_date": sun_date,
                "error": "TeamUp M2M API token is not configured yet. Add your TeamUp API token or use 'Setup Next Sat/Sun Event' to configure slots.",
                "signup_groups": build_signup_groups_summary([]),
            }), 400

        client = TeamUpClient(api_token=cfg["api_token"], provider_id=cfg["provider_id"], base_url=cfg["base_url"])
        try:
            sat_date, sun_date, remote_events, attendances = _fetch_weekend_teamup_signups(
                client,
                sat_date,
                sun_date,
                query=data.get("query") or args.get("query"),
                event_ids=data.get("teamup_event_ids") or args.get("teamup_event_ids"),
                status=data.get("status") or args.get("status") or "registered",
            )
        except TeamUpAPIError as e:
            return jsonify({
                "ok": False,
                "configured": True,
                "error": e.message,
                "details": e.details,
                "signup_groups": build_signup_groups_summary([]),
            }), (e.status_code if 400 <= e.status_code < 600 else 502)

    mapped_entries = []
    for att in (attendances or []):
        if not _is_weekend_hyrox_sim_attendance(att):
            continue
        mapped = map_teamup_attendance_to_entry(att)
        if not mapped or not mapped.get("display_name"):
            continue
        att_status = mapped.get("teamup_attendance_status", "registered")
        if att_status in ("late_cancelled", "not_registered", "cancelled", "removed"):
            continue
        mapped_entries.append(mapped)

    groups_summary = build_signup_groups_summary(mapped_entries)
    return jsonify({
        "ok": True,
        "configured": teamup_configured,
        "saturday_date": sat_date,
        "sunday_date": sun_date,
        "total_signups": len(mapped_entries),
        "signup_groups": groups_summary,
        "entries": mapped_entries,
        "remote_events_count": len(remote_events),
        "remote_events": remote_events,
    })


@hyrox_bp.route("/api/hyrox/events/setup-weekend", methods=["POST"])
def api_setup_weekend_event():
    """
    Create or update the 2-Day Weekend HYROX Event for Next Saturday & Sunday:
      - Saturday (Day 1, 14:00 - 17:00):
          1. Male Solo (14:00 - 15:20, 1:1 slots)
          2. Male Doubles / Mixed Doubles (15:30 - 16:50, 1:1 slots)
      - Sunday (Day 2, 10:00 - 14:00):
          3. Female Solo (10:00 - 11:50, 1:1 slots)
          4. Female Doubles (12:00 - 13:50, 1:1 slots)
    Optionally syncs TeamUp sign-ups directly into those 4 blocks.
    """
    db = get_db()
    ensure_hyrox_tables(db)
    data = request.get_json(silent=True) or {}

    sat_default, sun_default = get_next_weekend_dates()
    sat_date = (data.get("saturday_date") or data.get("event_date") or sat_default).strip()
    sun_date = (data.get("sunday_date") or data.get("end_date") or sun_default).strip()
    interval_mins = max(int(data.get("interval_mins") or 5), 1)
    transition_buffer_mins = int(data.get("transition_buffer_mins") if data.get("transition_buffer_mins") is not None else 10)

    try:
        sat_dt = datetime.strptime(sat_date, "%Y-%m-%d")
        sun_dt = datetime.strptime(sun_date, "%Y-%m-%d")
        default_name = f"CS Performance HYROX Weekend — Sat {sat_dt.strftime('%d %b')} & Sun {sun_dt.strftime('%d %b %Y')}"
    except Exception:
        default_name = f"CS Performance HYROX Weekend — {sat_date} & {sun_date}"

    ev_name = (data.get("name") or default_name).strip()
    target_event_id = data.get("event_id")

    if target_event_id:
        ev_row = db.execute("SELECT * FROM hyrox_events WHERE id=?", (int(target_event_id),)).fetchone()
        if not ev_row:
            return jsonify({"error": "Event not found"}), 404
        event_id = ev_row["id"]
        db.execute(
            "UPDATE hyrox_events SET name=?, event_date=?, end_date=?, num_days=2, wave_interval_mins=?, "
            "lanes_per_wave=1, transition_buffer_mins=?, status='live' WHERE id=?",
            (ev_name, sat_date, sun_date, interval_mins, transition_buffer_mins, event_id),
        )
    else:
        existing_ev = db.execute(
            "SELECT * FROM hyrox_events WHERE event_date=? AND end_date=? ORDER BY id DESC LIMIT 1",
            (sat_date, sun_date),
        ).fetchone()
        if existing_ev and not data.get("force_new"):
            event_id = existing_ev["id"]
            db.execute(
                "UPDATE hyrox_events SET name=?, wave_interval_mins=?, lanes_per_wave=1, "
                "transition_buffer_mins=?, num_days=2, status='live' WHERE id=?",
                (ev_name, interval_mins, transition_buffer_mins, event_id),
            )
        else:
            cur_ev = db.execute(
                "INSERT INTO hyrox_events (name, event_date, end_date, num_days, venue, wave_interval_mins, "
                "lanes_per_wave, transition_buffer_mins, status, notes) "
                "VALUES (?, ?, ?, 2, 'CS Performance Studio', ?, 1, ?, 'live', ?)",
                (
                    ev_name,
                    sat_date,
                    sun_date,
                    interval_mins,
                    transition_buffer_mins,
                    "Saturday 14:00–17:00 (1. Male Solo · 2. Male Doubles / Mixed Doubles) | "
                    "Sunday 10:00–14:00 (3. Female Solo · 4. Female Doubles)",
                ),
            )
            event_id = cur_ev.lastrowid

    if data.get("clear_empty_heats", True):
        db.execute(
            "DELETE FROM hyrox_heats WHERE event_id=? AND id NOT IN "
            "(SELECT DISTINCT heat_id FROM hyrox_entries WHERE event_id=? AND heat_id IS NOT NULL)",
            (event_id, event_id),
        )

    # Generate the 4 Weekend Blocks (Saturday 14:00-17:00 & Sunday 09:30-14:00)
    # Saturday 14:00-15:20: 1. Male Solo (9 slots @ 10m = 14:00..15:20)
    # Saturday 15:30-16:50: 2. Male Doubles / Mixed Doubles (9 slots @ 10m = 15:30..16:50)
    # Sunday 09:30-11:50:   3. Female Solo (15 slots @ 10m = 09:30..11:50, or 29 slots @ 5m = 09:30..11:50)
    # Sunday 12:00-13:50:   4. Female Doubles (12 slots @ 10m = 12:00..13:50)
    sat_solo_slots = int(data.get("male_solo_slots") or max(1, (90 // interval_mins)))
    sat_doubles_slots = int(data.get("male_mixed_doubles_slots") or max(1, (90 // interval_mins)))
    sun_solo_slots = int(data.get("female_solo_slots") or max(1, (150 // interval_mins)))
    sun_doubles_slots = int(data.get("female_doubles_slots") or max(1, (120 // interval_mins)))

    blocks_spec = [
        (1, sat_date, "men_open", data.get("sat_solo_start") or "14:00", sat_solo_slots, transition_buffer_mins),
        (1, sat_date, "men_doubles", data.get("sat_doubles_start") or "15:30", sat_doubles_slots, 0),
        (2, sun_date, "women_open", data.get("sun_solo_start") or "09:30", sun_solo_slots, transition_buffer_mins),
        (2, sun_date, "women_doubles", data.get("sun_doubles_start") or "12:00", sun_doubles_slots, 0),
    ]

    created_heat_ids = []
    for day_num, s_date, div_blk, st_time, count, buf in blocks_spec:
        start_mins = _hm_to_mins(st_time, 14 * 60 if day_num == 1 else 10 * 60)
        div_label = HYROX_DIVISIONS.get(div_blk, {}).get("label", "")
        grp_label = HYROX_SIGNUP_GROUPS[division_to_signup_group_key(div_blk)]["short_label"]
        for i in range(count):
            t_str = _mins_to_hm(start_mins + i * interval_mins)
            exists = db.execute(
                "SELECT id FROM hyrox_heats WHERE event_id=? AND COALESCE(day_number, 1)=? AND start_time=? LIMIT 1",
                (event_id, day_num, t_str),
            ).fetchone()
            if exists:
                continue
            existing_max = db.execute(
                "SELECT COALESCE(MAX(heat_number), 0) as m FROM hyrox_heats WHERE event_id=?",
                (event_id,),
            ).fetchone()["m"]
            h_num = existing_max + 1
            h_name = f"Day {day_num} · {t_str} — {grp_label}"
            buf_after = buf if (i == count - 1) else 0
            cur_h = db.execute(
                "INSERT INTO hyrox_heats (event_id, heat_number, day_number, slot_date, division_block, "
                "transition_buffer_mins, name, start_time, max_lanes, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'scheduled')",
                (event_id, h_num, day_num, s_date, div_blk, buf_after, h_name, t_str),
            )
            created_heat_ids.append(cur_h.lastrowid)

    # Optional: Sync TeamUp sign-ups or inline `attendances` into the 4 weekend blocks
    synced_ids = []
    teamup_sync_error = None
    attendances = data.get("attendances")
    should_sync_teamup = data.get("sync_teamup", True)
    cfg = get_teamup_config(db)

    if attendances is None and should_sync_teamup and cfg["has_token"]:
        client = TeamUpClient(api_token=cfg["api_token"], provider_id=cfg["provider_id"], base_url=cfg["base_url"])
        try:
            _, _, _, attendances = _fetch_weekend_teamup_signups(
                client, sat_date, sun_date, status="registered"
            )
        except TeamUpAPIError as e:
            teamup_sync_error = e.message

    for att in (attendances or []):
        if not _is_weekend_hyrox_sim_attendance(att):
            continue
        mapped = map_teamup_attendance_to_entry(att)
        if not mapped or not mapped.get("display_name"):
            continue
        if mapped.get("teamup_attendance_status") in ("late_cancelled", "not_registered", "cancelled", "removed"):
            continue
        _assign_weekend_group_slot(db, event_id, mapped, interval_mins=interval_mins)
        eid, _ = _create_entry_record(db, event_id, mapped, upsert=True)
        if eid:
            synced_ids.append(eid)

    db.commit()
    ev_final = db.execute("SELECT * FROM hyrox_events WHERE id=?", (event_id,)).fetchone()
    heats_final = [
        dict(h)
        for h in db.execute(
            "SELECT * FROM hyrox_heats WHERE event_id=? ORDER BY day_number ASC, start_time ASC, heat_number ASC",
            (event_id,),
        ).fetchall()
    ]
    entry_rows = db.execute("SELECT * FROM hyrox_entries WHERE event_id=? ORDER BY id ASC", (event_id,)).fetchall()
    entries_final = [serialize_entry(db, r, include_splits=False, include_history=False) for r in entry_rows]

    return jsonify({
        "ok": True,
        "event": dict(ev_final),
        "saturday_date": sat_date,
        "sunday_date": sun_date,
        "heats_created_count": len(created_heat_ids),
        "heats_total_count": len(heats_final),
        "synced_count": len(synced_ids),
        "teamup_sync_error": teamup_sync_error,
        "entries": entries_final,
        "signup_groups": build_signup_groups_summary(entries_final),
    }), 201


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
    assign_weekend_blocks = data.get("assign_weekend_blocks", True)
    stagger_start_time = (data.get("stagger_start_time") or "").strip()
    interval_mins = int(data.get("interval_mins") or ev["wave_interval_mins"] or 5)

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
            ev_end = (ev["end_date"] if "end_date" in ev.keys() and ev["end_date"] else ev_date)
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

    # Clean up any previously imported non-simulation regular gym class entries on this event
    _purge_non_sim_teamup_entries(db, event_id=event_id)

    synced_ids = []
    cancelled_ids = []
    skipped = 0
    stagger_idx = 0
    explicit_event_filter = bool(data.get("teamup_event_ids") or data.get("teamup_event_id"))

    for att in (attendances or []):
        if not explicit_event_filter and not _is_weekend_hyrox_sim_attendance(att):
            skipped += 1
            continue
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

        if auto_stagger and stagger_start_time:
            base_hm = stagger_start_time or mapped.get("heat_time") or "08:00"
            m_hm = re.match(r"^(\d{1,2}):(\d{2})$", base_hm)
            base_mins = (int(m_hm.group(1)) * 60 + int(m_hm.group(2))) if m_hm else 8 * 60
            slot_mins = base_mins + (stagger_idx * interval_mins)
            mapped["heat_time"] = f"{(slot_mins // 60) % 24:02d}:{slot_mins % 60:02d}"
            stagger_idx += 1
        elif assign_weekend_blocks and int(ev["lanes_per_wave"] or 1) == 1:
            _assign_weekend_group_slot(db, event_id, mapped, interval_mins=interval_mins)

        eid, err = _create_entry_record(db, event_id, mapped, upsert=True)
        if eid:
            synced_ids.append(eid)
        else:
            skipped += 1

    _apply_road_to_glasgow_enrichment_to_db(db, event_id=event_id)
    db.commit()
    entry_rows = db.execute("SELECT * FROM hyrox_entries WHERE event_id=? ORDER BY id ASC", (event_id,)).fetchall()
    entries_final = [serialize_entry(db, r, include_splits=False, include_history=False) for r in entry_rows]
    return jsonify({
        "ok": True,
        "synced_count": len(synced_ids),
        "cancelled_count": len(cancelled_ids),
        "skipped_count": skipped,
        "synced_entry_ids": synced_ids,
        "cancelled_entry_ids": cancelled_ids,
        "signup_groups": build_signup_groups_summary(entries_final),
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

