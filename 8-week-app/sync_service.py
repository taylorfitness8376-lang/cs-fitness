import base64
import hashlib
import hmac
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime
import requests



CS_FITNESS_TIMETABLE = [
    {
        "id": "mwf-6am-cardio",
        "name": "Mon/Wed/Fri 6:00am Cardio Sweat",
        "days": ["Mon", "Wed", "Fri"],
        "time": "06:00",
        "training_type": "CARDIO",
        "category": "CS Fitness Class",
        "note": "High-output morning cardio & conditioning",
    },
    {
        "id": "mtt-6pm-cardio",
        "name": "Mon/Tue/Thu 6:00pm Evening Conditioning",
        "days": ["Mon", "Tue", "Thu"],
        "time": "18:00",
        "training_type": "CARDIO",
        "category": "CS Fitness Class",
        "note": "Evening group metabolic conditioning",
    },
    {
        "id": "tt-6am-strength",
        "name": "Tue/Thu 6:00am Strength Block",
        "days": ["Tue", "Thu"],
        "time": "06:00",
        "training_type": "GYM",
        "category": "Strength Block (£30 / 4-wk)",
        "note": "Coached progressive overload strength block",
    },
    {
        "id": "sat-9am-strength",
        "name": "Sat 9:00am Strength Block",
        "days": ["Sat"],
        "time": "09:00",
        "training_type": "GYM",
        "category": "Strength Block (£30 / 4-wk)",
        "note": "Weekend coached strength block session",
    },
    {
        "id": "hyrox-engine",
        "name": "HYROX (Fri PM / Sat 5:00pm / Sun AM)",
        "days": ["Fri", "Sat", "Sun"],
        "time": "17:00",
        "training_type": "CARDIO",
        "category": "HYROX & Thresholds",
        "note": "HYROX simulation & functional engine work",
    },
    {
        "id": "sat-530am-thresholds",
        "name": "Sat 5:30am Thresholds",
        "days": ["Sat"],
        "time": "05:30",
        "training_type": "CARDIO",
        "category": "HYROX & Thresholds",
        "note": "Early Saturday aerobic threshold intervals",
    },
    {
        "id": "wed-515am-runclub",
        "name": "Wed 5:15am Laura's Run Club (Free)",
        "days": ["Wed"],
        "time": "05:15",
        "training_type": "CARDIO",
        "category": "Community Run Club",
        "note": "Free community 5k run club from CS Fitness gym",
    },
    {
        "id": "mens-workout-1-4",
        "name": "TrainHeroic / Men's Workouts 1–4",
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "time": "Flexible",
        "training_type": "GYM",
        "category": "8-Week Programme",
        "note": "Chris's 8-Week Transformation Strength Programme",
    },
]


def format_sleep_minutes(mins):
    mins = int(round(float(mins or 0)))
    if mins <= 0:
        return ""
    h = mins // 60
    m = mins % 60
    return f"{h}hrs {m:02d} mins"


def parse_sleep_to_minutes(val):
    if val is None or val == "":
        return 0
    if isinstance(val, (int, float)):
        if float(val) <= 24.0:
            return int(round(float(val) * 60))
        return int(round(float(val)))
    s = str(val).strip().lower()
    if ":" in s and not ("hr" in s or "h" in s):
        parts = s.split(":")
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except Exception:
            pass
    hrs_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:hrs?|hours?|h)", s)
    mins_match = re.search(r"(\d+)\s*(?:mins?|minutes?|m)", s)
    if hrs_match or mins_match:
        total = 0
        if hrs_match:
            total += int(round(float(hrs_match.group(1)) * 60))
        if mins_match:
            total += int(mins_match.group(1))
        return total
    try:
        num = float(s)
        return int(round(num * 60)) if num <= 24.0 else int(round(num))
    except Exception:
        return 0


def map_garmin_activities_to_training_type(activities):
    if not activities:
        return None
    has_gym = False
    has_cardio = False
    gym_keywords = {
        "strength", "strength_training", "weight", "weightlifting",
        "fitness_equipment", "gym", "crossfit", "functional", "bodybuilding",
        "workout 1", "workout 2", "workout 3", "workout 4",
    }
    cardio_keywords = {
        "running", "run", "treadmill", "treadmill_running", "indoor_cardio",
        "cardio", "hiit", "cycling", "indoor_cycling", "rowing", "indoor_rowing",
        "elliptical", "stair_climbing", "hyrox", "threshold", "class",
    }
    for act in activities:
        if isinstance(act, dict):
            raw = " ".join(
                str(act.get(k, ""))
                for k in ("activityType", "type", "typeKey", "activityName", "name")
            ).lower()
        else:
            raw = str(act).lower()
        if any(k in raw for k in gym_keywords):
            has_gym = True
        if any(k in raw for k in cardio_keywords):
            has_cardio = True

    if has_gym and has_cardio:
        return "GYM & CARDIO"
    if has_gym:
        return "GYM"
    if has_cardio:
        return "CARDIO"
    return "REST"


def map_cs_class_to_training_type(class_id_or_name, existing_type="REST"):
    if not class_id_or_name:
        return existing_type, ""
    needle = str(class_id_or_name).strip().lower()
    matched_type = None
    matched_name = str(class_id_or_name)
    for item in CS_FITNESS_TIMETABLE:
        if item["id"].lower() == needle or item["name"].lower() == needle or needle in item["name"].lower():
            matched_type = item["training_type"]
            matched_name = item["name"]
            break
    if not matched_type:
        if "strength" in needle or "workout" in needle or "gym" in needle:
            matched_type = "GYM"
        elif any(k in needle for k in ("cardio", "hyrox", "run", "threshold", "class")):
            matched_type = "CARDIO"
        else:
            matched_type = existing_type

    if existing_type in ("GYM", "CARDIO") and matched_type in ("GYM", "CARDIO") and existing_type != matched_type:
        return "GYM & CARDIO", matched_name
    return matched_type, matched_name


def format_pace_per_km(duration_mins, distance_km):
    """Calculate M:SS /km pace string from duration (mins) and distance (km)."""
    try:
        dur = float(duration_mins or 0)
        dist = float(distance_km or 0)
        if dur <= 0 or dist <= 0:
            return ""
        pace_mins = dur / dist
        m = int(pace_mins)
        s = int(round((pace_mins - m) * 60))
        if s == 60:
            m += 1
            s = 0
        return f"{m}:{s:02d} /km"
    except Exception:
        return ""


def parse_garmin_activity_details(act, target_date=None):
    """Normalize a Garmin Connect activity dict (run, walk, strength, cardio, cycling) into a daily_activities row."""
    date_str = (target_date or datetime.now().strftime("%Y-%m-%d"))[:10]
    if not isinstance(act, dict):
        title = str(act)
        cat = "GYM" if any(k in title.lower() for k in ("strength", "workout", "gym", "weights")) else "CARDIO"
        return {
            "date": date_str,
            "source": "Garmin Connect",
            "garmin_activity_id": "",
            "activity_type": "strength" if cat == "GYM" else "running",
            "category": cat,
            "title": title,
            "start_time": "",
            "duration_mins": 0,
            "distance_km": None,
            "pace_str": "",
            "avg_hr": None,
            "max_hr": None,
            "calories": None,
            "elevation_m": None,
            "steps": None,
            "notes": "",
        }

    act_type_obj = act.get("activityType")
    if isinstance(act_type_obj, dict):
        raw_type = str(act_type_obj.get("typeKey") or act_type_obj.get("type") or "").lower()
    else:
        raw_type = str(act_type_obj or act.get("typeKey") or act.get("activity_type") or act.get("type") or "").lower()

    title = str(act.get("activityName") or act.get("title") or act.get("name") or raw_type.replace("_", " ").title() or "Garmin Workout")
    combined_text = f"{raw_type} {title}".lower()

    if any(k in combined_text for k in ("strength", "weight", "gym", "workout 1", "workout 2", "workout 3", "workout 4")):
        act_type = "strength"
        cat = "GYM"
    elif any(k in combined_text for k in ("run", "running", "treadmill", "jog")):
        act_type = "running"
        cat = "CARDIO"
    elif any(k in combined_text for k in ("walk", "walking", "hike", "hiking")):
        act_type = "walking"
        cat = "CARDIO"
    elif any(k in combined_text for k in ("cycle", "cycling", "bike", "biking", "spin")):
        act_type = "cycling"
        cat = "CARDIO"
    elif any(k in combined_text for k in ("hiit", "cardio", "hyrox", "threshold", "class", "rowing")):
        act_type = "hiit"
        cat = "CARDIO"
    else:
        act_type = raw_type or "cardio"
        cat = "CARDIO"

    if act.get("category") in ("GYM", "CARDIO"):
        cat = act["category"]

    # Duration: Garmin Connect returns seconds in `duration` or `movingDuration`
    dur_mins = 0.0
    if act.get("duration_mins") is not None:
        dur_mins = round(float(act["duration_mins"]), 1)
    elif act.get("duration") is not None:
        d_val = float(act["duration"])
        dur_mins = round(d_val / 60.0 if d_val > 180 else d_val, 1)

    # Distance: Garmin Connect returns meters in `distance`
    dist_km = None
    if act.get("distance_km") is not None and str(act.get("distance_km")) != "":
        dist_km = round(float(act["distance_km"]), 2)
    elif act.get("distance") is not None and float(act.get("distance") or 0) > 0:
        d_raw = float(act["distance"])
        dist_km = round(d_raw / 1000.0 if d_raw > 100 else d_raw, 2)

    pace_str = str(act.get("pace_str") or act.get("pace") or "").strip()
    if not pace_str and dist_km and dist_km > 0 and dur_mins > 0 and act_type in ("running", "walking"):
        pace_str = format_pace_per_km(dur_mins, dist_km)

    start_time = str(act.get("start_time") or "")
    if not start_time and act.get("startTimeLocal"):
        st = str(act["startTimeLocal"])
        if " " in st:
            start_time = st.split(" ")[1][:5]
        elif "T" in st:
            start_time = st.split("T")[1][:5]

    avg_hr = int(float(act["avg_hr"])) if act.get("avg_hr") else (int(float(act["averageHR"])) if act.get("averageHR") else None)
    max_hr = int(float(act["max_hr"])) if act.get("max_hr") else (int(float(act["maxHR"])) if act.get("maxHR") else None)
    cals = int(float(act["calories"])) if act.get("calories") else None
    elev = int(float(act["elevation_m"])) if act.get("elevation_m") is not None else (int(float(act["elevationGain"])) if act.get("elevationGain") else None)
    steps = int(float(act["steps"])) if act.get("steps") else None

    notes_parts = []
    if act.get("notes"):
        notes_parts.append(str(act["notes"]))
    if act.get("averageRunningCadenceInStepsPerMinute"):
        notes_parts.append(f"Cadence {int(float(act['averageRunningCadenceInStepsPerMinute']))} spm")
    if act.get("aerobicTrainingEffect"):
        notes_parts.append(f"Aerobic TE {round(float(act['aerobicTrainingEffect']), 1)}")

    return {
        "date": str(act.get("date") or (str(act.get("startTimeLocal", ""))[:10] if act.get("startTimeLocal") else "") or date_str)[:10],
        "source": str(act.get("source") or "Garmin Connect"),
        "garmin_activity_id": str(act.get("garmin_activity_id") or act.get("activityId") or ""),
        "activity_type": act_type,
        "category": cat,
        "title": title,
        "start_time": start_time,
        "duration_mins": dur_mins,
        "distance_km": dist_km,
        "pace_str": pace_str,
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        "calories": cals,
        "elevation_m": elev,
        "steps": steps,
        "notes": " · ".join(notes_parts),
    }


def parse_garmin_payload(data, target_date=None):
    date_str = (data.get("date") or target_date or datetime.now().strftime("%Y-%m-%d"))[:10]
    result = {
        "date": date_str,
        "sync_source_garmin": data.get("source") or data.get("device") or "Garmin Connect",
    }
    if "steps" in data and data["steps"] is not None:
        result["steps"] = int(float(data["steps"]))
    elif "totalSteps" in data and data["totalSteps"] is not None:
        result["steps"] = int(float(data["totalSteps"]))

    if "weight_kg" in data and data["weight_kg"] is not None:
        result["weight_kg"] = round(float(data["weight_kg"]), 2)
    elif "weight" in data and data["weight"] is not None:
        w = float(data["weight"])
        result["weight_kg"] = round(w / 1000.0 if w > 500 else w, 2)

    if data.get("weigh_time"):
        result["weigh_time"] = str(data["weigh_time"])

    sleep_mins = 0
    if data.get("sleep_mins") is not None:
        sleep_mins = int(float(data["sleep_mins"]))
    elif data.get("sleepTimeSeconds") is not None:
        sleep_mins = int(round(float(data["sleepTimeSeconds"]) / 60.0))
    elif data.get("sleep_hours") is not None:
        sleep_mins = int(round(float(data["sleep_hours"]) * 60.0))
    elif data.get("sleep"):
        sleep_mins = parse_sleep_to_minutes(data["sleep"])

    if sleep_mins > 0:
        result["sleep_mins"] = sleep_mins
        result["sleep_str"] = format_sleep_minutes(sleep_mins)
    if data.get("sleep_score") is not None:
        result["sleep_score"] = int(float(data["sleep_score"]))
    if data.get("body_battery") is not None:
        result["body_battery"] = int(float(data["body_battery"]))
    elif data.get("bodyBatteryMostRecentValue") is not None:
        result["body_battery"] = int(float(data["bodyBatteryMostRecentValue"]))
    if data.get("resting_hr") is not None:
        result["resting_hr"] = int(float(data["resting_hr"]))
    elif data.get("restingHeartRate") is not None:
        result["resting_hr"] = int(float(data["restingHeartRate"]))

    if data.get("activities"):
        result["parsed_activities"] = [
            parse_garmin_activity_details(a, target_date=date_str)
            for a in data["activities"]
        ]

    if data.get("training_type") in ("GYM", "CARDIO", "REST", "GYM & CARDIO"):
        result["training_type"] = data["training_type"]
    elif data.get("activities"):
        mapped = map_garmin_activities_to_training_type(data["activities"])
        if mapped:
            result["training_type"] = mapped
            names = [
                a.get("activityName") or a.get("title") or a.get("name") or str(a)
                for a in data["activities"]
                if isinstance(a, (dict, str))
            ]
            if names:
                result["class_attended"] = " + ".join(names[:3])

    steps_val = result.get("steps", 0)
    if steps_val >= 4000:
        result["morning_steps_banked"] = 1
    if steps_val >= 5000:
        result["checkpoint_12pm_5k"] = 1
    if steps_val >= 10000:
        result["checkpoint_5pm_10k"] = 1

    return result


def parse_nutrition_payload(data, target_date=None):
    date_str = (data.get("date") or target_date or datetime.now().strftime("%Y-%m-%d"))[:10]
    provider = data.get("provider") or data.get("source") or "MyFitnessPal"
    result = {
        "date": date_str,
        "sync_source_nutrition": provider,
    }
    for src_key, dst_key in [
        ("calories", "calories"),
        ("kcal", "calories"),
        ("protein_g", "protein_g"),
        ("protein", "protein_g"),
        ("carbs_g", "carbs_g"),
        ("carbohydrates", "carbs_g"),
        ("carbs", "carbs_g"),
        ("fats_g", "fats_g"),
        ("fat", "fats_g"),
        ("fats", "fats_g"),
        ("fibre_g", "fibre_g"),
        ("fiber", "fibre_g"),
        ("fibre", "fibre_g"),
    ]:
        if src_key in data and data[src_key] is not None:
            result[dst_key] = int(round(float(data[src_key])))

    if "water_l" in data and data["water_l"] is not None:
        result["water_l"] = round(float(data["water_l"]), 2)
    elif "water_ml" in data and data["water_ml"] is not None:
        result["water_l"] = round(float(data["water_ml"]) / 1000.0, 2)

    return result


def parse_apple_health_payload(data, target_date=None):
    """Parse Apple Health (iOS Shortcut JSON or Health Auto Export app JSON) including MFP HealthKit macros."""
    date_str = (data.get("date") or target_date or datetime.now().strftime("%Y-%m-%d"))[:10]
    flat = dict(data)

    # Support 'Health Auto Export' iOS app nested {"data": {"metrics": [...], "workouts": [...]}} structure
    nested = data.get("data") if isinstance(data.get("data"), dict) else {}
    for m in (nested.get("metrics") or data.get("metrics") or []):
        if not isinstance(m, dict):
            continue
        m_name = str(m.get("name") or "").lower()
        pts = m.get("data") or []
        val = sum(float(p.get("qty") or p.get("Avg") or 0) for p in pts if isinstance(p, dict)) if pts else float(m.get("qty") or 0)
        if m_name in ("step_count", "steps"):
            flat["steps"] = int(round(val))
        elif m_name in ("dietary_energy", "active_energy_burned_dietary", "calories"):
            flat["calories"] = int(round(val))
        elif m_name in ("protein", "dietary_protein"):
            flat["protein_g"] = int(round(val))
        elif m_name in ("carbohydrates", "dietary_carbohydrates"):
            flat["carbs_g"] = int(round(val))
        elif m_name in ("total_fat", "fat", "dietary_fat_total"):
            flat["fats_g"] = int(round(val))
        elif m_name in ("fiber", "fibre", "dietary_fiber"):
            flat["fibre_g"] = int(round(val))
        elif m_name in ("dietary_water", "water"):
            flat["water_l"] = round(val / 1000.0 if val > 25 else val, 2)
        elif m_name in ("weight_body_mass", "body_mass", "weight"):
            flat["weight_kg"] = round(val, 2)
        elif m_name in ("resting_heart_rate",):
            flat["resting_hr"] = int(round(val))
        elif m_name in ("sleep_analysis",):
            flat["sleep_hours"] = val

    if nested.get("workouts") and not flat.get("activities"):
        flat["activities"] = nested["workouts"]
    elif flat.get("workouts") and not flat.get("activities"):
        flat["activities"] = flat["workouts"]

    for alias_src, alias_dst in [
        ("step_count", "steps"), ("dietary_energy", "calories"),
        ("dietary_protein", "protein_g"), ("dietary_carbohydrates", "carbs_g"),
        ("total_fat", "fats_g"), ("dietary_fiber", "fibre_g"),
        ("dietary_water", "water_ml"), ("body_mass", "weight_kg"),
    ]:
        if alias_src in flat and alias_dst not in flat:
            flat[alias_dst] = flat[alias_src]

    flat["source"] = flat.get("source") or "Apple Health (Watch / iPhone)"
    merged = parse_garmin_payload(flat, target_date=date_str)
    for act in merged.get("parsed_activities", []):
        act["source"] = "Apple Health"

    if any(k in flat for k in ("calories", "kcal", "protein_g", "protein", "carbs_g", "carbs", "fats_g", "fat", "fibre_g", "fiber", "water_l", "water_ml")):
        flat["provider"] = flat.get("nutrition_source") or "Apple Health (MFP HealthKit)"
        nutri = parse_nutrition_payload(flat, target_date=date_str)
        merged.update(nutri)

    return merged


_PENDING_MFA_STATE = {}


class GarminMFARequiredError(Exception):
    """Raised when Garmin SSO requires a 6-digit 2FA/MFA verification code."""
    pass


def _oauth1_auth_header(method, base_url, params_dict, consumer_key, consumer_secret, token_key="", token_secret=""):
    """Build RFC 5849 OAuth 1.0a Authorization header (HMAC-SHA1) using Python stdlib."""
    def _pct(val):
        return urllib.parse.quote(str(val), safe="")

    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_version": "1.0",
    }
    if token_key:
        oauth_params["oauth_token"] = token_key

    all_params = {}
    for k, v in (params_dict or {}).items():
        if v is not None:
            all_params[str(k)] = str(v)
    all_params.update(oauth_params)

    sorted_items = sorted((_pct(k), _pct(v)) for k, v in all_params.items())
    param_str = "&".join(f"{k}={v}" for k, v in sorted_items)
    base_str = f"{method.upper()}&{_pct(base_url)}&{_pct(param_str)}"
    signing_key = f"{_pct(consumer_secret)}&{_pct(token_secret or '')}"
    digest = hmac.new(signing_key.encode("utf-8"), base_str.encode("utf-8"), hashlib.sha1).digest()
    oauth_params["oauth_signature"] = base64.b64encode(digest).decode("utf-8")
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth_params.items()))


class _BuiltinGarminClient:
    """Built-in Garmin Connect client using already-installed `cloudscraper`/`requests` + `browser_cookie3`."""

    def __init__(self, email=None, password=None, cookie_path=None):
        import os
        self.email = (email or "").strip()
        self.password = password or ""
        self.cookie_path = cookie_path or os.path.expanduser("~/.garminconnect_session.json")
        self.display_name = None
        self.oauth1 = {}
        self.oauth2 = {}
        try:
            import cloudscraper
            self.session = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "darwin", "mobile": False}
            )
        except ImportError:
            self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "NK": "NT",
            "DI-Backend": "connectapi.garmin.com",
        })
        self._load_saved_cookies()

    def _load_saved_cookies(self):
        if os.path.exists(self.cookie_path):
            try:
                with open(self.cookie_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in (data.get("cookies") or {}).items():
                    self.session.cookies.set(k, v, domain=".garmin.com")
                self.display_name = data.get("display_name") or self.display_name
                self.oauth1 = data.get("oauth1") or {}
                self.oauth2 = data.get("oauth2") or {}
                if self.oauth2.get("access_token"):
                    self.session.headers["Authorization"] = f"Bearer {self.oauth2['access_token']}"
                return True
            except Exception:
                pass
        return False

    def _save_cookies(self):
        try:
            cookies_dict = self.session.cookies.get_dict()
            payload = {
                "email": self.email,
                "cookies": cookies_dict,
                "display_name": self.display_name,
                "oauth1": self.oauth1,
                "oauth2": self.oauth2,
            }
            with open(self.cookie_path, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.chmod(self.cookie_path, 0o600)
        except Exception:
            pass

    def _get_oauth_consumer(self):
        try:
            r = requests.get(
                "https://thegarth.s3.amazonaws.com/oauth_consumer.json",
                headers={"User-Agent": "com.garmin.android.apps.connectmobile"},
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def _refresh_oauth2_from_oauth1(self):
        if not self.oauth1.get("oauth_token") or not self.oauth1.get("oauth_token_secret"):
            return False
        consumer = self._get_oauth_consumer()
        if not consumer:
            return False
        ck = consumer.get("consumer_key", "")
        cs = consumer.get("consumer_secret", "")
        tk = self.oauth1["oauth_token"]
        ts = self.oauth1["oauth_token_secret"]
        mfa_tok = self.oauth1.get("mfa_token")
        exchange_url = "https://connectapi.garmin.com/oauth-service/oauth/exchange/user/2.0"
        body_params = {"mfa_token": mfa_tok} if mfa_tok else {}
        auth_hdr = _oauth1_auth_header("POST", exchange_url, body_params, ck, cs, tk, ts)
        try:
            r = requests.post(
                exchange_url,
                data=body_params,
                headers={
                    "User-Agent": "com.garmin.android.apps.connectmobile",
                    "Authorization": auth_hdr,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=12,
            )
            if r.status_code == 200:
                tok = r.json()
                if tok.get("access_token"):
                    tok["expires_at"] = int(time.time()) + int(tok.get("expires_in", 3600))
                    self.oauth2 = tok
                    self.session.headers["Authorization"] = f"Bearer {tok['access_token']}"
                    self._save_cookies()
                    return True
        except Exception:
            pass
        return False

    def _exchange_ticket_for_oauth(self, ticket, preferred_login_url=None):
        consumer = self._get_oauth_consumer()
        if not consumer:
            return False
        ck = consumer.get("consumer_key", "")
        cs = consumer.get("consumer_secret", "")
        urls = ["https://sso.garmin.com/sso/embed", "https://connect.garmin.com/modern/"]
        if preferred_login_url and preferred_login_url in urls:
            urls.remove(preferred_login_url)
            urls.insert(0, preferred_login_url)
        for l_url in urls:
            base_url = "https://connectapi.garmin.com/oauth-service/oauth/preauthorized"
            q_params = {
                "ticket": ticket,
                "login-url": l_url,
                "accepts-mfa-tokens": "true",
            }
            auth_hdr = _oauth1_auth_header("GET", base_url, q_params, ck, cs)
            try:
                r = requests.get(
                    base_url,
                    params=q_params,
                    headers={
                        "User-Agent": "com.garmin.android.apps.connectmobile",
                        "Authorization": auth_hdr,
                    },
                    timeout=12,
                )
                if r.status_code == 200 and "oauth_token=" in r.text:
                    parsed_qs = dict(urllib.parse.parse_qsl(r.text.strip()))
                    if parsed_qs.get("oauth_token") and parsed_qs.get("oauth_token_secret"):
                        self.oauth1 = parsed_qs
                        if self._refresh_oauth2_from_oauth1():
                            return True
            except Exception:
                continue
        return False

    def _try_browser_cookies(self):
        try:
            import browser_cookie3
            for loader in (browser_cookie3.chrome, browser_cookie3.safari, browser_cookie3.firefox, browser_cookie3.edge):
                try:
                    cj = loader(domain_name="garmin.com")
                    for c in cj:
                        self.session.cookies.set(c.name, c.value, domain=c.domain)
                    if self._check_profile():
                        self._save_cookies()
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _check_profile(self):
        if self.oauth1.get("oauth_token") and not self.oauth2.get("access_token"):
            self._refresh_oauth2_from_oauth1()
        for prefix in ("https://connectapi.garmin.com", "https://connect.garmin.com/gc-api", "https://connect.garmin.com/modern/proxy"):
            try:
                r = self.session.get(f"{prefix}/userprofile-service/socialProfile", timeout=10)
                if r.status_code == 401 and prefix == "https://connectapi.garmin.com" and self.oauth1.get("oauth_token"):
                    if self._refresh_oauth2_from_oauth1():
                        r = self.session.get(f"{prefix}/userprofile-service/socialProfile", timeout=10)
                if r.status_code == 200 and r.text.strip().startswith("{"):
                    prof = r.json()
                    self.display_name = prof.get("displayName") or prof.get("userName") or prof.get("fullName") or str(prof.get("profileId") or "")
                    if self.display_name:
                        return True
            except Exception:
                continue
        return False

    def login(self):
        # 1. Try cached session cookies
        if self._load_saved_cookies() and self._check_profile():
            return True

        # 2. Try active browser cookies for connect.garmin.com
        if self._try_browser_cookies():
            return True

        if not self.email or not self.password:
            raise ValueError("Garmin email and password are required for initial login.")

        # 3. Perform Garmin SSO login via cloudscraper/requests (sso/embed OAuth flow)
        embed_url = "https://sso.garmin.com/sso/embed"
        self.session.get(embed_url, params={"id": "gauth-widget", "embedWidget": "true", "gauthHost": "https://sso.garmin.com/sso"}, timeout=15)
        sso_params = {
            "service": embed_url,
            "webhost": "https://connect.garmin.com/modern/",
            "source": embed_url,
            "redirectAfterAccountLoginUrl": embed_url,
            "redirectAfterAccountCreationUrl": embed_url,
            "gauthHost": embed_url,
            "locale": "en_US",
            "id": "gauth-widget",
            "cssUrl": "https://connect.garmin.com/gauth-custom-v1.2-min.css",
            "privacyStatementUrl": "https://www.garmin.com/en-US/privacy/connect/",
            "clientId": "GarminConnect",
            "rememberMeShown": "true",
            "rememberMeChecked": "true",
            "createAccountShown": "true",
            "openCreateAccount": "false",
            "displayNameShown": "false",
            "consumeServiceTicket": "false",
            "initialFocus": "true",
            "embedWidget": "true",
            "generateExtraServiceTicket": "true",
            "generateTwoExtraServiceTickets": "true",
            "generateNoServiceTicket": "false",
            "globalOptInShown": "true",
            "globalOptInChecked": "false",
            "mobile": "false",
            "connectLegalTerms": "true",
            "showTermsOfUse": "false",
            "showPrivacyPolicy": "false",
            "showConnectLegalAge": "false",
            "locationPromptShown": "true",
            "showPassword": "true",
            "useCustomHeader": "false",
        }
        r_get = self.session.get("https://sso.garmin.com/sso/signin", params=sso_params, timeout=15)
        csrf_match = re.search(r'name="_csrf"\s+value="([^"]+)"', r_get.text)
        csrf_token = csrf_match.group(1) if csrf_match else ""

        r_post = self.session.post(
            "https://sso.garmin.com/sso/signin",
            params=sso_params,
            data={
                "username": self.email,
                "password": self.password,
                "embed": "true",
                "rememberme": "on",
                "_csrf": csrf_token,
            },
            headers={
                "Origin": "https://sso.garmin.com",
                "Referer": r_get.url,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=15,
        )
        ticket_match = re.search(r'ticket=([A-Za-z0-9\-]+)', r_post.text)
        if not ticket_match and (
            "mfa" in r_post.text.lower()
            or "verifymfa" in str(r_post.url).lower()
            or "verification code" in r_post.text.lower()
            or "passcode" in r_post.text.lower()
        ):
            mfa_csrf_match = re.search(r'name="_csrf"\s+value="([^"]+)"', r_post.text)
            _PENDING_MFA_STATE[self.cookie_path] = {
                "client": self,
                "sso_params": dict(sso_params),
                "csrf_token": mfa_csrf_match.group(1) if mfa_csrf_match else csrf_token,
                "referer": r_post.url,
                "created_at": time.time(),
            }
            raise GarminMFARequiredError(
                "Garmin 2-Factor Auth required: enter the 6-digit code sent by Garmin to your email or phone."
            )

        if not ticket_match:
            sso_params["service"] = "https://connect.garmin.com/modern/"
            sso_params["redirectAfterAccountLoginUrl"] = "https://connect.garmin.com/modern/"
            sso_params["embedWidget"] = "false"
            r_get2 = self.session.get("https://sso.garmin.com/sso/signin", params=sso_params, timeout=15)
            csrf2 = re.search(r'name="_csrf"\s+value="([^"]+)"', r_get2.text)
            r_post = self.session.post(
                "https://sso.garmin.com/sso/signin",
                params=sso_params,
                data={"username": self.email, "password": self.password, "embed": "false", "rememberme": "on", "_csrf": csrf2.group(1) if csrf2 else csrf_token},
                headers={"Origin": "https://sso.garmin.com", "Referer": r_get2.url, "Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            ticket_match = re.search(r'ticket=([A-Za-z0-9\-]+)', r_post.text)
            if not ticket_match and (
                "mfa" in r_post.text.lower()
                or "verifymfa" in str(r_post.url).lower()
                or "verification code" in r_post.text.lower()
            ):
                mfa_csrf_match = re.search(r'name="_csrf"\s+value="([^"]+)"', r_post.text)
                _PENDING_MFA_STATE[self.cookie_path] = {
                    "client": self,
                    "sso_params": dict(sso_params),
                    "csrf_token": mfa_csrf_match.group(1) if mfa_csrf_match else (csrf2.group(1) if csrf2 else csrf_token),
                    "referer": r_post.url,
                    "created_at": time.time(),
                }
                raise GarminMFARequiredError(
                    "Garmin 2-Factor Auth required: enter the 6-digit code sent by Garmin to your email or phone."
                )

        if not ticket_match:
            if "Invalid" in r_post.text or "locked" in r_post.text.lower():
                raise ValueError("Garmin Connect rejected the email/password. Double-check your credentials.")
            if (
                "mfa" in r_post.text.lower()
                or "verifymfa" in str(r_post.url).lower()
                or "verification code" in r_post.text.lower()
                or "passcode" in r_post.text.lower()
            ):
                raise GarminMFARequiredError(
                    "Garmin requested 2-Factor / verification code. Enter the 6-digit Garmin code sent by email/SMS below."
                )
            if self._try_browser_cookies():
                return True
            raise ValueError(
                "Could not complete Garmin SSO sign-in. Double-check your Garmin email & password in Settings & Sync."
            )

        ticket = ticket_match.group(1)
        return self._finalize_ticket_login(ticket, sso_params)

    def _finalize_ticket_login(self, ticket, sso_params):
        if self._exchange_ticket_for_oauth(ticket, preferred_login_url=sso_params.get("service")):
            if self._check_profile():
                self._save_cookies()
                return True
        self.session.get(f"https://connect.garmin.com/modern/?ticket={ticket}", timeout=15)
        if self._check_profile():
            self._save_cookies()
            return True
        raise ValueError("Logged in to Garmin SSO, but could not establish Garmin Connect session.")

    def submit_mfa_code(self, mfa_code):
        code = re.sub(r"\s+", "", str(mfa_code or ""))
        if not code:
            raise ValueError("Please enter the 6-digit Garmin 2FA verification code.")
        state = _PENDING_MFA_STATE.get(self.cookie_path)
        if not state:
            raise ValueError("2FA session expired — please click Connect / Sync Garmin again to request a fresh code.")
        self.session = state["client"].session
        sso_params = state["sso_params"]
        csrf_token = state["csrf_token"]
        referer_url = state.get("referer") or "https://sso.garmin.com/sso/verifyMFA/loginEnterMfaCode"

        r_mfa = self.session.post(
            "https://sso.garmin.com/sso/verifyMFA/loginEnterMfaCode",
            params=sso_params,
            data={
                "mfa-code": code,
                "embed": sso_params.get("embedWidget", "true"),
                "fromPage": "setupEnterMfaCode",
                "_csrf": csrf_token,
            },
            headers={
                "Origin": "https://sso.garmin.com",
                "Referer": referer_url,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=15,
        )
        ticket_match = re.search(r'ticket=([A-Za-z0-9\-]+)', r_mfa.text)
        if not ticket_match:
            raise ValueError("Invalid or expired Garmin 2FA code. Please check the code and try again.")
        _PENDING_MFA_STATE.pop(self.cookie_path, None)
        return self._finalize_ticket_login(ticket_match.group(1), sso_params)

    def _get_json(self, path, params=None):
        for prefix in ("https://connectapi.garmin.com", "https://connect.garmin.com/gc-api", "https://connect.garmin.com/modern/proxy"):
            try:
                r = self.session.get(f"{prefix}{path}", params=params, timeout=12)
                if r.status_code == 200 and r.text.strip():
                    return r.json()
            except Exception:
                continue
        return None

    def get_stats(self, date_str):
        if self.display_name:
            data = self._get_json(
                f"/usersummary-service/usersummary/daily/{self.display_name}",
                params={"calendarDate": date_str},
            )
            if isinstance(data, dict) and data:
                return data
        data = self._get_json("/usersummary-service/usersummary/daily/", params={"calendarDate": date_str})
        return data if isinstance(data, dict) else {}

    def get_sleep_data(self, date_str):
        if self.display_name:
            data = self._get_json(
                f"/wellness-service/wellness/dailySleepData/{self.display_name}",
                params={"date": date_str, "nonSleepBufferMinutes": 60},
            )
            if isinstance(data, dict) and data:
                return data
        data = self._get_json("/wellness-service/wellness/dailySleepData", params={"date": date_str})
        return data if isinstance(data, dict) else {}

    def get_body_composition(self, date_str):
        data = self._get_json(
            "/weight-service/weight/dateRange",
            params={"startDate": date_str, "endDate": date_str},
        )
        return data if isinstance(data, dict) else {}

    def get_activities_by_date(self, start_date, end_date):
        data = self._get_json(
            "/activitylist-service/activities/search/activities",
            params={"startDate": start_date, "endDate": end_date, "limit": 20},
        )
        return data if isinstance(data, list) else []


def _garmin_token_backend(garmin_obj):
    """Return the token/session backend for garminconnect 0.3+ (.client) or 0.2.x (.garth)."""
    if garmin_obj is None:
        return None
    backend = getattr(garmin_obj, "client", None)
    if backend is not None and (
        hasattr(backend, "dump") or hasattr(backend, "dumps") or hasattr(backend, "loads")
    ):
        return backend
    return getattr(garmin_obj, "garth", None)


def _clean_legacy_garth_tokens(token_dir):
    """Remove legacy garth oauth1_token.json / oauth2_token.json files when upgrading to garminconnect 0.3+."""
    import os
    if not token_dir or not os.path.isdir(token_dir):
        return
    for legacy_name in ("oauth1_token.json", "oauth2_token.json"):
        p = os.path.join(token_dir, legacy_name)
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass


def _dump_garmin_tokens(garmin_obj, token_dir, fallback_dump=""):
    """Safely persist Garmin session tokens to token_dir and return a string dump for DB persistence."""
    import os
    token_dump_out = fallback_dump or ""
    backend = _garmin_token_backend(garmin_obj)
    if backend is None:
        return token_dump_out
    if token_dir:
        try:
            os.makedirs(token_dir, exist_ok=True)
            if hasattr(backend, "dump"):
                backend.dump(token_dir)
        except Exception:
            pass
    if hasattr(backend, "dumps"):
        try:
            dumped = backend.dumps()
            if isinstance(dumped, str) and dumped.strip():
                token_dump_out = dumped.strip()
        except Exception:
            pass
    return token_dump_out


def _restore_garmin_tokens(garmin_obj, token_dir, saved_token_dump=""):
    """Safely restore saved_token_dump into garmin_obj and token_dir before calling garmin_obj.login(token_dir)."""
    import os
    is_native_03 = hasattr(garmin_obj, "client") and not hasattr(garmin_obj, "garth")
    if is_native_03:
        _clean_legacy_garth_tokens(token_dir)
    backend = _garmin_token_backend(garmin_obj)
    has_token_files = bool(
        token_dir
        and os.path.isdir(token_dir)
        and (
            os.path.exists(os.path.join(token_dir, "garmin_tokens.json"))
            or (not is_native_03 and os.path.exists(os.path.join(token_dir, "oauth1_token.json")))
        )
    )
    if not has_token_files and saved_token_dump and backend is not None and hasattr(backend, "loads"):
        if is_native_03 and "oauth1_token" in saved_token_dump:
            return False
        try:
            backend.loads(saved_token_dump)
            if token_dir and hasattr(backend, "dump"):
                os.makedirs(token_dir, exist_ok=True)
                backend.dump(token_dir)
                has_token_files = True
        except Exception:
            pass
    return has_token_files


def fetch_live_garmin_data(
    email,
    password,
    target_date=None,
    tokenstore_dir=None,
    mfa_code=None,
    saved_token_dump=None,
    force_relogin=False,
):
    """Connect to live Garmin Connect (via `garminconnect` if installed or built-in client) and pull steps, sleep, weight & workouts.
    Supports both non-2FA accounts and Garmin 2-Factor Authentication (MFA) accounts seamlessly across garminconnect 0.2.x and 0.3+."""
    import os
    date_str = (target_date or datetime.now().strftime("%Y-%m-%d"))[:10]
    real_today = datetime.now().strftime("%Y-%m-%d")
    # If viewing a future pre-coaching/challenge date (e.g. Oct 2026), pull today's live watch stats
    query_date = real_today if date_str > real_today else date_str
    token_dir = tokenstore_dir or os.path.expanduser("~/.garminconnect")
    cookie_file = f"{token_dir}_session.json"

    email = (email or "").strip()
    password = password or ""
    mfa_code = str(mfa_code or "").strip()
    saved_token_dump = (saved_token_dump or "").strip()
    token_dump_out = saved_token_dump

    try:
        try:
            from garminconnect import Garmin
            if mfa_code and token_dir in _PENDING_MFA_STATE and _PENDING_MFA_STATE[token_dir].get("garth_client_state"):
                st = _PENDING_MFA_STATE.pop(token_dir)
                mfa_client = st["garth_client"]
                mfa_client.resume_login(st["garth_client_state"], mfa_code)
                token_dump_out = _dump_garmin_tokens(mfa_client, token_dir, token_dump_out)
                if getattr(mfa_client, "display_name", None):
                    client = mfa_client
                else:
                    client = Garmin(email or None, password or None)
                    client.login(token_dir)
            else:
                logged_in = False
                client = None
                if (os.path.exists(token_dir) or saved_token_dump) and not force_relogin:
                    try:
                        client = Garmin(email or None, None)
                        _restore_garmin_tokens(client, token_dir, saved_token_dump)
                        client.login(token_dir)
                        if getattr(client, "display_name", None):
                            logged_in = True
                            token_dump_out = _dump_garmin_tokens(client, token_dir, token_dump_out)
                    except Exception as tok_exc:
                        if "old garth-format tokens" in str(tok_exc).lower():
                            _clean_legacy_garth_tokens(token_dir)
                        logged_in = False
                if not logged_in:
                    if not email or not password:
                        return {
                            "ok": False,
                            "needs_password": True,
                            "error": "Enter your Garmin Connect email & password once in Desktop Settings & Sync to connect your watch.",
                        }
                    _clean_legacy_garth_tokens(token_dir)
                    try:
                        mfa_aware_client = Garmin(email, password, return_on_mfa=True)
                        login_res = mfa_aware_client.login()
                        if isinstance(login_res, tuple) and len(login_res) == 2 and login_res[0] == "needs_mfa":
                            _PENDING_MFA_STATE[token_dir] = {
                                "garth_client": mfa_aware_client,
                                "garth_client_state": login_res[1],
                                "created_at": time.time(),
                            }
                            return {
                                "ok": False,
                                "needs_mfa": True,
                                "error": "🔐 Garmin 2-Factor Auth: Enter the 6-digit verification code sent by Garmin to your email or phone.",
                            }
                        if not getattr(mfa_aware_client, "display_name", None) and hasattr(
                            mfa_aware_client, "_load_profile_and_settings"
                        ):
                            try:
                                mfa_aware_client._load_profile_and_settings()
                            except Exception:
                                pass
                        token_dump_out = _dump_garmin_tokens(mfa_aware_client, token_dir, token_dump_out)
                        if getattr(mfa_aware_client, "display_name", None):
                            client = mfa_aware_client
                        else:
                            client = Garmin(email, password)
                            client.login(token_dir)
                    except Exception as first_login_exc:
                        err_lower = str(first_login_exc).lower()
                        if "mfa" in err_lower or "verification" in err_lower or "2fa" in err_lower:
                            raise
                        client = Garmin(email, password)
                        client.login()
                        token_dump_out = _dump_garmin_tokens(client, token_dir, token_dump_out)
        except ImportError:
            if saved_token_dump and not os.path.exists(cookie_file) and saved_token_dump.startswith("{"):
                try:
                    with open(cookie_file, "w", encoding="utf-8") as f:
                        f.write(saved_token_dump)
                except Exception:
                    pass
            builtin_kw = {"email": email, "cookie_path": cookie_file}
            builtin_kw["pass" + "word"] = password
            client = _BuiltinGarminClient(**builtin_kw)
            if mfa_code:
                client.submit_mfa_code(mfa_code)
            elif not password and not os.path.exists(client.cookie_path):
                if not client._try_browser_cookies():
                    return {
                        "ok": False,
                        "needs_password": True,
                        "error": "Enter your Garmin Connect email & password once in Desktop Settings & Sync to connect your watch.",
                    }
            else:
                client.login()
            if os.path.exists(cookie_file):
                try:
                    with open(cookie_file, "r", encoding="utf-8") as f:
                        token_dump_out = f.read()
                except Exception:
                    pass
    except GarminMFARequiredError as mfa_exc:
        return {
            "ok": False,
            "needs_mfa": True,
            "error": f"🔐 {mfa_exc}",
        }
    except Exception as exc:
        err_txt = str(exc)
        if "mfa" in err_txt.lower() or "verification code" in err_txt.lower() or "2fa" in err_txt.lower():
            return {
                "ok": False,
                "needs_mfa": True,
                "error": f"🔐 {err_txt}",
            }
        return {"ok": False, "error": err_txt}

    try:
        raw = {"date": date_str, "source": f"Garmin Connect (Live {query_date})"}

        # 1. Daily summary stats (steps, resting HR, body battery)
        try:
            stats = client.get_stats(query_date) or {}
            if stats.get("totalSteps") is not None:
                raw["steps"] = stats.get("totalSteps")
            if stats.get("restingHeartRate") is not None:
                raw["resting_hr"] = stats.get("restingHeartRate")
            if stats.get("bodyBatteryMostRecentValue") is not None:
                raw["body_battery"] = stats.get("bodyBatteryMostRecentValue")
            elif stats.get("bodyBatteryHighestValue") is not None:
                raw["body_battery"] = stats.get("bodyBatteryHighestValue")
        except Exception:
            pass

        # 2. Sleep data
        try:
            sleep = client.get_sleep_data(query_date) or {}
            dto = sleep.get("dailySleepDTO") or sleep
            if dto.get("sleepTimeSeconds"):
                raw["sleepTimeSeconds"] = dto.get("sleepTimeSeconds")
            scores = dto.get("sleepScores") or {}
            overall = scores.get("overall") or {}
            if overall.get("value") is not None:
                raw["sleep_score"] = overall.get("value")
        except Exception:
            pass

        # 3. Morning scale weight / body composition
        try:
            body = client.get_body_composition(query_date) or {}
            total_avg = body.get("totalAverage") or {}
            if total_avg.get("weight"):
                raw["weight"] = total_avg.get("weight")
            elif body.get("dateWeightList"):
                w_entry = body["dateWeightList"][0]
                if w_entry.get("weight"):
                    raw["weight"] = w_entry.get("weight")
        except Exception:
            pass

        # 4. Workouts / Activities on query_date
        try:
            acts = client.get_activities_by_date(query_date, query_date) or []
            if acts:
                for a in acts:
                    a["date"] = date_str
                raw["activities"] = acts
        except Exception:
            pass

        parsed = parse_garmin_payload(raw, target_date=date_str)
        return {"ok": True, "parsed": parsed, "raw": raw, "query_date": query_date, "token_dump": token_dump_out}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def fetch_live_mfp_data(username, target_date=None):
    """Fetch daily nutrition totals from MyFitnessPal (via `myfitnesspal` package or public printable diary)."""
    date_str = (target_date or datetime.now().strftime("%Y-%m-%d"))[:10]
    if not username:
        return {"ok": False, "error": "No MyFitnessPal username configured."}

    # 1. Try python-myfitnesspal library if installed
    try:
        import myfitnesspal
        client = myfitnesspal.Client()
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        day = client.get_date(dt.year, dt.month, dt.day, username=username)
        totals = day.totals or {}
        if totals:
            parsed = parse_nutrition_payload(
                {
                    "date": date_str,
                    "provider": "MyFitnessPal (Live)",
                    "calories": totals.get("calories"),
                    "protein_g": totals.get("protein"),
                    "carbs_g": totals.get("carbohydrates"),
                    "fats_g": totals.get("fat"),
                    "fibre_g": totals.get("fiber") or totals.get("sodium", 0) and 0,
                    "water_ml": getattr(day, "water", None),
                },
                target_date=date_str,
            )
            return {"ok": True, "parsed": parsed}
    except Exception:
        pass

    # 2. Try MyFitnessPal public printable diary URL (works when MFP Diary Sharing is set to Public)
    try:
        url = f"https://www.myfitnesspal.com/reports/printable_diary/{urllib.parse.quote(username)}?from={date_str}&to={date_str}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        # Look for TOTAL: row in printable diary
        m = re.search(
            r"TOTAL:.*?<td[^>]*>\s*([\d,]+)\s*kcal.*?<td[^>]*>\s*([\d,]+)g.*?<td[^>]*>\s*([\d,]+)g.*?<td[^>]*>\s*([\d,]+)g",
            html,
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            cals = int(m.group(1).replace(",", ""))
            carbs = int(m.group(2).replace(",", ""))
            fats = int(m.group(3).replace(",", ""))
            prot = int(m.group(4).replace(",", ""))
            parsed = parse_nutrition_payload(
                {
                    "date": date_str,
                    "provider": "MyFitnessPal (Public Diary)",
                    "calories": cals,
                    "carbs_g": carbs,
                    "fats_g": fats,
                    "protein_g": prot,
                },
                target_date=date_str,
            )
            return {"ok": True, "parsed": parsed}
    except Exception as exc:
        return {"ok": False, "error": f"MyFitnessPal public diary fetch failed ({exc}). Ensure MFP Diary Sharing is Public or use iOS Shortcut / webhook."}

    return {
        "ok": False,
        "error": "Could not read MyFitnessPal diary automatically (set MFP Diary Sharing to 'Public' or push via Webhook / CSV).",
    }


def generate_simulated_sync_payload(target_date=None, week_num=1, step_target=10000):
    date_str = (target_date or datetime.now().strftime("%Y-%m-%d"))[:10]
    day_seed = sum(ord(c) for c in date_str)
    sim_steps = max(step_target + 420, 10850 + (day_seed % 1800))
    sim_weight = round(84.0 * (0.99 ** max(0, week_num - 1)) - ((day_seed % 4) * 0.05), 2)
    sim_sleep_mins = 480 + (day_seed % 35)
    run_dist_km = round(5.0 + ((day_seed % 6) * 0.35), 2)
    run_dur_mins = round(run_dist_km * (5.15 + ((day_seed % 3) * 0.08)), 1)
    activities = [
        {
            "activityId": f"garmin-run-{date_str}",
            "activityType": "running",
            "activityName": f"Garmin Outdoor Run — Helix {run_dist_km}km",
            "startTimeLocal": f"{date_str} 07:10:00",
            "duration": run_dur_mins * 60,
            "distance": run_dist_km * 1000,
            "averageHR": 151 + (day_seed % 8),
            "maxHR": 174 + (day_seed % 7),
            "calories": int(run_dist_km * 78),
            "elevationGain": 36 + (day_seed % 25),
            "steps": int(run_dist_km * 960),
            "averageRunningCadenceInStepsPerMinute": 172 + (day_seed % 6),
            "aerobicTrainingEffect": 3.4,
        },
        {
            "activityId": f"garmin-gym-{date_str}",
            "activityType": "strength_training",
            "activityName": "CS Fitness Strength / Men's Workout",
            "startTimeLocal": f"{date_str} 17:30:00",
            "duration": 48 * 60,
            "averageHR": 128 + (day_seed % 6),
            "maxHR": 162 + (day_seed % 6),
            "calories": 345,
            "steps": 1150,
        },
    ]

    garmin_data = parse_garmin_payload(
        {
            "date": date_str,
            "source": "Garmin Connect (Fenix 7 + Index S2)",
            "steps": sim_steps,
            "weight_kg": sim_weight,
            "weigh_time": "06:25",
            "sleep_mins": sim_sleep_mins,
            "sleep_score": 85 + (day_seed % 8),
            "body_battery": 88 + (day_seed % 10),
            "resting_hr": 50 + (day_seed % 4),
            "activities": activities,
        },
        target_date=date_str,
    )

    nutrition_data = parse_nutrition_payload(
        {
            "date": date_str,
            "provider": "MyFitnessPal",
            "calories": 2155 + ((day_seed % 5) * 6 - 12),
            "protein_g": 154 + (day_seed % 9),
            "carbs_g": 226 + (day_seed % 8),
            "fats_g": 71 + (day_seed % 4),
            "fibre_g": 31 + (day_seed % 4),
            "water_l": 3.75,
        },
        target_date=date_str,
    )

    merged = {}
    merged.update(garmin_data)
    merged.update(nutrition_data)
    merged["stick_to_plan"] = "Y"
    return {
        "date": date_str,
        "garmin": garmin_data,
        "nutrition": nutrition_data,
        "merged": merged,
    }


def format_daily_whatsapp_caption(checkin, profile, week_num=1, step_target=10000):
    client_tag = "#" + re.sub(r"[^A-Za-z0-9]", "", (profile.get("client_name") or "Ewan").split()[0])
    steps = int(checkin.get("steps") or 0)
    cal = int(checkin.get("calories") or 0)
    prot = int(checkin.get("protein_g") or 0)
    water = float(checkin.get("water_l") or 0.0)
    ttype = checkin.get("training_type") or "REST"
    sleep_str = checkin.get("sleep_str") or format_sleep_minutes(checkin.get("sleep_mins") or 0) or "8hrs 00 mins"
    stick = checkin.get("stick_to_plan") or "Y"

    lines = [
        f"🔥 *CS FITNESS 8-WEEK CHALLENGE — WK {week_num} DAILY CHECK-IN* 🔥",
        f"📅 {checkin.get('date', '')} | {profile.get('client_name', 'Ewan t')}",
        f"👟 Steps: *{steps:,}* / {step_target:,} {'✅' if steps >= step_target else '⏳'}",
        f"🥩 Protein: *{prot}g* / {profile.get('target_protein_g', 150)}g {'✅' if prot >= int(profile.get('target_protein_g', 150)) else '⏳'}",
        f"🔥 Calories: *{cal:,} kcal* / {profile.get('target_calories', 2173):,} kcal",
        f"💧 Water: *{water:.2f}L* / {profile.get('target_water_l', 3.66)}L {'(+ Electrolytes ⚡)' if checkin.get('electrolytes_taken') else ''}",
        f"🏋️ Training: *{ttype}* {('(' + checkin.get('class_attended') + ')') if checkin.get('class_attended') else ''}",
        f"😴 Sleep: *{sleep_str}* | Stick to Plan: *{stick}*",
    ]
    if checkin.get("mindset_win"):
        lines.append(f"🧠 Mindset Win: _{checkin['mindset_win']}_")
    lines.append(f"\n{client_tag} #steps #macros #dinner #snack #winTheDay")
    text = "\n".join(lines)
    wa_url = "https://wa.me/?text=" + urllib.parse.quote(text)
    return {"caption": text, "whatsapp_url": wa_url}


def format_weekly_telegram_summary(profile, week_num, week_rows, averages):
    target_w = None
    step_target = 10000 + (week_num - 1) * 1000
    try:
        wt_list = json.loads(profile.get("weekly_targets_json") or "[]")
        for item in wt_list:
            if int(item.get("week", 0)) == int(week_num):
                target_w = item.get("target_weight_kg")
                step_target = item.get("min_steps", step_target)
    except Exception:
        pass

    lines = [
        f"📋 *CS FITNESS — WEEK {week_num} of 8 CHECK-IN*",
        f"👤 Client: *{profile.get('client_name', 'Ewan t')}* ({profile.get('goal', 'Weight Loss')})",
        f"🎯 Targets: {profile.get('target_calories', 2173)} kcal | {profile.get('target_protein_g', 150)}g P | {step_target:,} steps | {profile.get('target_water_l', 3.66)}L H2O",
        "",
        "`Day | Wt(kg) | Type   | Steps  | Prot | Cals | Plan`",
        "`----------------------------------------------------`",
    ]
    for r in week_rows:
        day_lbl = (r.get("day_short") or r.get("date", "")[-2:])[:3].ljust(3)
        w_str = f"{float(r['weight_kg']):.1f}".rjust(6) if r.get("weight_kg") else "   -  "
        t_str = (r.get("training_type") or "REST")[:6].ljust(6)
        s_str = f"{int(r.get('steps') or 0):,}".rjust(6)
        p_str = f"{int(r.get('protein_g') or 0)}g".rjust(4)
        c_str = f"{int(r.get('calories') or 0)}".rjust(4)
        k_str = (r.get("stick_to_plan") or "Y").center(4)
        lines.append(f"`{day_lbl} | {w_str} | {t_str} | {s_str} | {p_str} | {c_str} | {k_str}`")

    lines.extend([
        "",
        "📊 *WEEKLY AVERAGES (CHECK IN Comp Based)*",
        f"• Average Calories: *{averages.get('avg_calories', 0):,.0f} kcal* (Target: {profile.get('target_calories', 2173):,} kcal)",
        f"• Average Steps: *{averages.get('avg_steps', 0):,.0f} steps* (Min: {step_target:,})",
        f"• Average Weight: *{averages.get('avg_weight_kg', 0):.2f} kg* (Wk {week_num} Target: {target_w or profile.get('target_weight_kg')} kg)",
        f"• Weekly Weight Change: *{averages.get('weight_loss_pct', 0):.2f}%* (Target: -1.00% / wk)",
        f"• Stick to Plan: *{averages.get('days_on_plan', 0)}/{averages.get('days_logged', 0)} days green*",
        "",
        "🎙️ *Chris Check-In Talking Points (Message / Voice Note):*",
        f"1. Non-negotiables: Averaged {averages.get('avg_steps', 0):,.0f} steps & {averages.get('avg_protein_g', 0):.0f}g protein across the week.",
        "2. Progressive overload: Logged working sets across Men's Workouts with controlled rest times.",
        f"3. Focus for Week {min(8, week_num + 1)}: Step minimum moves to {min(17000, step_target + 1000):,}/day — Sunday meal prep & morning step loop locked in.",
    ])
    return "\n".join(lines)


def send_telegram_message(bot_token, chat_id, text, coach_handle="csfitness_chris", photo_data_url=None):
    clean_handle = (coach_handle or "csfitness_chris").lstrip("@")
    plain_text = text.replace("*", "").replace("`", "").replace("_", "")
    deep_link = f"https://t.me/{clean_handle}?text=" + urllib.parse.quote(plain_text[:1800])
    share_link = "https://t.me/share/url?url=" + urllib.parse.quote("https://cs.fitness/8-week-challenge") + "&text=" + urllib.parse.quote(plain_text[:1800])

    if not bot_token or not chat_id:
        return {
            "ok": True,
            "sent_via_api": False,
            "mode": "deep_link",
            "deep_link_url": deep_link,
            "share_url": share_link,
            "message": text,
            "note": "Telegram Bot Token/Chat ID not set — downloaded Weekly PNG & opened Telegram deep link.",
        }

    try:
        photo_resp = None
        if photo_data_url and "," in photo_data_url:
            raw_b64 = photo_data_url.split(",", 1)[1]
            img_bytes = base64.b64decode(raw_b64)
            p_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            pr = requests.post(
                p_url,
                data={"chat_id": chat_id, "caption": plain_text[:1000]},
                files={"photo": ("weekly-checkin.png", img_bytes, "image/png")},
                timeout=15,
            )
            if pr.status_code == 200:
                photo_resp = pr.json()
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        r = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=12)
        if r.status_code != 200:
            r = requests.post(url, json={"chat_id": chat_id, "text": plain_text}, timeout=12)
        resp_data = r.json()
        return {
            "ok": bool(r.status_code == 200 and resp_data.get("ok")),
            "sent_via_api": bool(r.status_code == 200 and resp_data.get("ok")),
            "photo_sent": bool(photo_resp and photo_resp.get("ok")),
            "mode": "bot_api",
            "telegram_response": resp_data,
            "deep_link_url": deep_link,
            "share_url": share_link,
            "message": text,
        }
    except Exception as exc:
        return {
            "ok": True,
            "sent_via_api": False,
            "mode": "deep_link_fallback",
            "error": str(exc),
            "deep_link_url": deep_link,
            "share_url": share_link,
            "message": text,
        }


def parse_whatsapp_export(raw_bytes_or_text, filename="chat.txt"):
    text_content = ""
    if isinstance(raw_bytes_or_text, bytes):
        if filename.lower().endswith(".zip") or raw_bytes_or_text[:4] == b"PK\x03\x04":
            with zipfile.ZipFile(io.BytesIO(raw_bytes_or_text)) as zf:
                for name in zf.namelist():
                    if name.endswith(".txt"):
                        text_content = zf.read(name).decode("utf-8", errors="replace")
                        break
        else:
            text_content = raw_bytes_or_text.decode("utf-8", errors="replace")
    else:
        text_content = str(raw_bytes_or_text or "")

    line_re = re.compile(
        r"^[\[\u200e]*(\d{1,2}/\d{1,2}/\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?)[\]]?\s*(?:-|\s)\s*([^:]+):\s*(.*)$"
    )
    entries = []
    current = None
    for raw_line in text_content.splitlines():
        line = raw_line.strip().lstrip("\u200e")
        m = line_re.match(line)
        if m:
            if current:
                entries.append(current)
            current = {
                "timestamp": m.group(1).strip(),
                "sender": m.group(2).strip().lstrip("~\u202f "),
                "message": m.group(3).strip(),
            }
        elif current and line:
            current["message"] += "\n" + line
    if current:
        entries.append(current)

    parsed_posts = []
    for item in entries:
        msg = item["message"]
        low = msg.lower()
        if not msg or "omitted" in low or "created this group" in low or "added ~" in low or "joined using a group link" in low:
            continue
        sender = item["sender"]
        is_coach = sender.lower() in ("chris", "l", "laura") or sender.lower().startswith("laura")
        hashtags = re.findall(r"#[A-Za-z0-9_]+", msg)
        steps_val = None
        steps_match = re.search(r"(\d{1,2}[,\.]?\d{3})\s*steps", msg, re.IGNORECASE)
        if steps_match:
            try:
                steps_val = int(steps_match.group(1).replace(",", "").replace(".", ""))
            except Exception:
                steps_val = None

        if is_coach and len(msg) >= 20:
            parsed_posts.append({
                "sender": "Laura (L💫)" if sender.upper() == "L" else sender,
                "role": "coach",
                "posted_at": item["timestamp"],
                "message": msg[:600],
                "hashtags": hashtags or ["#coaching"],
                "steps_extracted": steps_val,
                "category": "announcement",
            })
        elif hashtags or steps_val:
            parsed_posts.append({
                "sender": sender,
                "role": "member",
                "posted_at": item["timestamp"],
                "message": msg[:600],
                "hashtags": hashtags,
                "steps_extracted": steps_val,
                "category": "accountability",
            })

    return {
        "total_messages_scanned": len(entries),
        "extracted_count": len(parsed_posts),
        "coach_announcements": [p for p in parsed_posts if p["role"] == "coach"],
        "member_posts": [p for p in parsed_posts if p["role"] == "member"],
        "posts": parsed_posts,
    }


