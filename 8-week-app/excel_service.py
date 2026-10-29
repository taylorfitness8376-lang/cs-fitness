"""Coach Chris Excel (.xlsx) Generator, Importer & HEIC Photo Normalizer.

Preserves 100% of Coach Chris's original `Ewan t.xlsx` workbook structure:
- Sheet 1: `Front Sheet` (client stats, formulas, 8-week weight & step targets, daily macro/water targets)
- Sheet 2: `CHECK IN SINGLE PRINT` (single-week printable sheet for the selected week)
- Sheet 3: `CHECK IN Comp Based` (12-week cumulative daily check-in tracker + Column M weekly averages)
- Sheet 4: `Mens Workouts` (Workouts 1-4 across Weeks 1-8 in columns H..O)
- Sheet 5: `Ladies Workouts` (Workouts 1-4 across Weeks 1-8 in columns H..O)
- Sheet 6: `Exercises` (exercise library reference)
All 8 embedded CS Fitness JPEG logos, 28 conditional formatting rules, and dropdown validations remain intact.
"""

import base64
from datetime import date, datetime, timedelta
from html import escape as xml_escape
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile


EXCEL_EPOCH = date(1899, 12, 30)
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS = {"s": MAIN_NS}

ET.register_namespace("", MAIN_NS)
ET.register_namespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
ET.register_namespace("mc", "http://schemas.openxmlformats.org/markup-compatibility/2006")
ET.register_namespace("x14ac", "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac")
ET.register_namespace("xr", "http://schemas.microsoft.com/office/spreadsheetml/2014/revision")
ET.register_namespace("xr2", "http://schemas.microsoft.com/office/spreadsheetml/2015/revision2")
ET.register_namespace("xr3", "http://schemas.microsoft.com/office/spreadsheetml/2016/revision3")

# Exact row mapping in Coach Chris's Mens Workouts (sheet4.xml) and Ladies Workouts (sheet5.xml)
MENS_ROW_KEY_TO_EXCEL_ROW = {
    "W1_A_1": 12,
    "W1_A_2": 13,
    "W1_A_3": 14,
    "W1_A_4": 15,
    "W1_B_1": 17,
    "W1_B_2": 18,
    "W1_B_3": 19,
    "W1_B_4": 20,
    "W1_C_1": 22,
    "W1_C_2": 23,
    "W1_C_3": 24,
    "W1_D1_1": 26,
    "W1_D2_1": 27,
    "W1_E1_1": 30,
    "W1_E2_1": 31,
    "W2_A_1": 37,
    "W2_A_2": 38,
    "W2_B_1": 40,
    "W2_B_2": 41,
    "W2_C1_1": 43,
    "W2_C2_1": 44,
    "W2_D1_1": 46,
    "W2_D2_1": 47,
    "W2_D3_1": 48,
    "W2_E1_1": 50,
    "W2_E2_1": 51,
    "W3_A_1": 57,
    "W3_A_2": 58,
    "W3_A_3": 59,
    "W3_B_1": 61,
    "W3_C_1": 63,
    "W3_D1_1": 66,
    "W3_D2_1": 67,
    "W3_E1_1": 69,
    "W4_A_1": 76,
    "W4_A_2": 77,
    "W4_B_1": 79,
    "W4_C_1": 81,
    "W4_D1_1": 84,
    "W4_D2_1": 85,
    "W4_E1_1": 87,
    "W4_E2_1": 88,
}

LADIES_ROW_KEY_TO_EXCEL_ROW = {
    "LW1_A_1": 12,
    "LW1_B_1": 15,
    "LW1_C_1": 17,
    "LW1_D1_1": 20,
    "LW1_D2_1": 21,
    "LW1_E1_1": 23,
    "LW1_E2_1": 24,
    "LW1_E3_1": 25,
    "LW2_A_1": 31,
    "LW2_B_1": 33,
    "LW2_C1_1": 35,
    "LW2_C2_1": 36,
    "LW2_D1_1": 38,
    "LW2_D2_1": 39,
    "LW2_E1_1": 41,
    "LW2_E2_1": 42,
    "LW3_A_1": 48,
    "LW3_B_1": 50,
    "LW3_C_1": 52,
    "LW3_D1_1": 55,
    "LW3_D2_1": 58,
    "LW3_E1_1": 62,
    "LW3_E2_1": 64,
    "LW4_A_1": 71,
    "LW4_B_1": 73,
    "LW4_C_1": 76,
    "LW4_D1_1": 80,
    "LW4_D2_1": 81,
    "LW4_E_1": 83,
    "LW4_F_1": 86,
}

MENS_EXCEL_ROW_TO_KEY = {v: k for k, v in MENS_ROW_KEY_TO_EXCEL_ROW.items()}
LADIES_EXCEL_ROW_TO_KEY = {v: k for k, v in LADIES_ROW_KEY_TO_EXCEL_ROW.items()}


def _find_template_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "data", "chris_checkin_template.xlsx"),
        os.path.join(os.path.dirname(here), "data", "chris_checkin_template.xlsx"),
        os.path.expanduser("~/Downloads/Ewan t.xlsx"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Coach Chris Excel template (chris_checkin_template.xlsx) not found")


def _iso_to_excel_serial(iso_str: str) -> int:
    dt = datetime.strptime(str(iso_str)[:10], "%Y-%m-%d").date()
    return (dt - EXCEL_EPOCH).days


def _excel_serial_to_iso(serial_val) -> str:
    try:
        days = int(round(float(serial_val)))
        if 40000 <= days <= 60000:
            return (EXCEL_EPOCH + timedelta(days=days)).strftime("%Y-%m-%d")
    except Exception:
        pass
    return ""


def _time_to_excel_serial(time_str: str):
    s = str(time_str or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{1,2})[:.](\d{2})", s)
    if m:
        hh = max(0, min(23, int(m.group(1))))
        mm = max(0, min(59, int(m.group(2))))
        return round((hh * 60 + mm) / 1440.0, 10)
    return None


def _excel_serial_to_time_str(val) -> str:
    try:
        f = float(val)
        if 0.0 <= f < 1.0:
            tot_mins = int(round(f * 1440))
            return f"{(tot_mins // 60) % 24:02d}:{tot_mins % 60:02d}"
    except Exception:
        pass
    return str(val or "").strip()


def _format_sleep_for_chris(sleep_str: str, sleep_mins: int) -> str:
    s = str(sleep_str or "").strip()
    if s and s != "0":
        return s
    mins = int(sleep_mins or 0)
    if mins > 0:
        return f"{mins // 60}hrs {mins % 60:02d} mins"
    return ""


def _normalize_training_type_for_chris(raw_type: str) -> str:
    t = str(raw_type or "").strip().upper()
    if t in ("GYM", "CARDIO", "REST", "GYM & CARDIO"):
        return t
    if "GYM" in t and "CARDIO" in t:
        return "GYM & CARDIO"
    if "GYM" in t or "STRENGTH" in t or "WEIGHT" in t:
        return "GYM"
    if "CARDIO" in t or "RUN" in t or "CLASS" in t or "HIIT" in t:
        return "CARDIO"
    return "REST"


class _SharedStringsTable:
    """Manages reading and appending to xl/sharedStrings.xml while preserving rich text."""

    def __init__(self, raw_xml_bytes: bytes):
        self.raw_xml_text = raw_xml_bytes.decode("utf-8")
        root = ET.fromstring(raw_xml_bytes)
        self.strings = []
        self.str_to_idx = {}
        for idx, si in enumerate(root.findall("s:si", NS)):
            txt = "".join(t.text or "" for t in si.findall(".//s:t", NS))
            self.strings.append(txt)
            if txt not in self.str_to_idx:
                self.str_to_idx[txt] = idx
        self.new_strings = []

    def get_or_add(self, text: str) -> int:
        s = str(text or "")
        if s in self.str_to_idx:
            return self.str_to_idx[s]
        idx = len(self.strings)
        self.strings.append(s)
        self.str_to_idx[s] = idx
        self.new_strings.append(s)
        return idx

    def to_xml_bytes(self) -> bytes:
        if not self.new_strings:
            return self.raw_xml_text.encode("utf-8")
        extra_nodes = "".join(
            f'<si><t xml:space="preserve">{xml_escape(s)}</t></si>'
            for s in self.new_strings
        )
        total_unique = len(self.strings)
        updated = re.sub(r'uniqueCount="\d+"', f'uniqueCount="{total_unique}"', self.raw_xml_text, count=1)
        updated = updated.replace("</sst>", f"{extra_nodes}</sst>")
        return updated.encode("utf-8")


def _set_cell_Blank(cell_el):
    if "t" in cell_el.attrib:
        del cell_el.attrib["t"]
    v_el = cell_el.find("s:v", NS)
    if v_el is not None:
        cell_el.remove(v_el)


def _set_cell_number(cell_el, num_val, keep_formula: bool = True):
    if num_val is None or num_val == "":
        if not keep_formula:
            f_el = cell_el.find("s:f", NS)
            if f_el is not None:
                cell_el.remove(f_el)
        _set_cell_Blank(cell_el)
        return
    if "t" in cell_el.attrib:
        del cell_el.attrib["t"]
    if not keep_formula:
        f_el = cell_el.find("s:f", NS)
        if f_el is not None:
            cell_el.remove(f_el)
    v_el = cell_el.find("s:v", NS)
    if v_el is None:
        v_el = ET.SubElement(cell_el, f"{{{MAIN_NS}}}v")
    if isinstance(num_val, float):
        if num_val.is_integer():
            v_el.text = str(int(num_val))
        else:
            v_el.text = f"{num_val:.10g}"
    else:
        v_el.text = str(num_val)


def _set_cell_string(cell_el, text_val: str, sst: _SharedStringsTable, keep_formula: bool = False):
    s = str(text_val or "")
    if not s:
        if not keep_formula:
            f_el = cell_el.find("s:f", NS)
            if f_el is not None:
                cell_el.remove(f_el)
        _set_cell_Blank(cell_el)
        return
    if not keep_formula:
        f_el = cell_el.find("s:f", NS)
        if f_el is not None:
            cell_el.remove(f_el)
    cell_el.set("t", "s")
    v_el = cell_el.find("s:v", NS)
    if v_el is None:
        v_el = ET.SubElement(cell_el, f"{{{MAIN_NS}}}v")
    v_el.text = str(sst.get_or_add(s))


def _set_cell_formula_cached(cell_el, cached_val, is_string: bool = False, sst: _SharedStringsTable = None):
    if is_string and sst is not None:
        cell_el.set("t", "str")
        v_el = cell_el.find("s:v", NS)
        if v_el is None:
            v_el = ET.SubElement(cell_el, f"{{{MAIN_NS}}}v")
        v_el.text = str(cached_val)
    elif cached_val == "#DIV/0!":
        cell_el.set("t", "e")
        v_el = cell_el.find("s:v", NS)
        if v_el is None:
            v_el = ET.SubElement(cell_el, f"{{{MAIN_NS}}}v")
        v_el.text = "#DIV/0!"
    else:
        _set_cell_number(cell_el, cached_val, keep_formula=True)


def _splice_sheet_data(raw_sheet_bytes: bytes, sheet_root) -> bytes:
    """Replace only <sheetData>...</sheetData> in raw_sheet_bytes so drawings, conditionalFormatting & namespaces stay 100% intact."""
    raw_text = raw_sheet_bytes.decode("utf-8")
    sheet_data_el = sheet_root.find("s:sheetData", NS)
    new_sheet_data_xml = ET.tostring(sheet_data_el, encoding="unicode")
    # Strip redundant xmlns declaration on <sheetData> since <worksheet> already declares the default namespace
    new_sheet_data_xml = re.sub(
        r'^<sheetData\s+xmlns="http://schemas\.openxmlformats\.org/spreadsheetml/2006/main"',
        "<sheetData",
        new_sheet_data_xml,
        count=1,
    )
    pattern = re.compile(r"<sheetData\b[^>]*>.*?</sheetData>", re.DOTALL)
    if not pattern.search(raw_text):
        raise ValueError("Could not locate <sheetData> in worksheet XML")
    updated_text = pattern.sub(lambda _m: new_sheet_data_xml, raw_text, count=1)
    return updated_text.encode("utf-8")


def _index_cells(sheet_root) -> dict:
    cells = {}
    for c in sheet_root.findall(".//s:sheetData/s:row/s:c", NS):
        ref = c.attrib.get("r")
        if ref:
            cells[ref] = c
    return cells


def _has_meaningful_day_data(c_row: dict, day_acts: list) -> bool:
    if not c_row and not day_acts:
        return False
    if c_row.get("weight_kg") is not None and float(c_row.get("weight_kg") or 0) > 0:
        return True
    if int(c_row.get("steps") or 0) > 0:
        return True
    if int(c_row.get("calories") or 0) > 0:
        return True
    if int(c_row.get("protein_g") or 0) > 0:
        return True
    if int(c_row.get("sleep_mins") or 0) > 0 or (c_row.get("sleep_str") and c_row.get("sleep_str") != "0"):
        return True
    if (c_row.get("notes") or "").strip():
        return True
    if (c_row.get("mindset_win") or "").strip():
        return True
    if day_acts:
        return True
    return False


def _build_day_notes(c_row: dict, day_acts: list, extra_note: str = "") -> str:
    notes = str((c_row or {}).get("notes") or "").strip()
    class_att = str((c_row or {}).get("class_attended") or "").strip()
    if not notes and class_att:
        notes = class_att
    elif class_att and class_att not in notes:
        notes = f"{notes} ({class_att})"
    if not notes and day_acts:
        titles = [str(a.get("title") or "").strip() for a in day_acts if str(a.get("title") or "").strip()]
        if titles:
            notes = " + ".join(dict.fromkeys(titles))
    mindset = str((c_row or {}).get("mindset_win") or "").strip()
    if mindset and mindset not in notes:
        notes = f"{notes} · {mindset}" if notes else mindset
    if extra_note and extra_note not in notes:
        notes = f"{notes} | {extra_note}" if notes else extra_note
    return notes


def generate_chris_excel_bytes(db, profile: dict, selected_week: int = None) -> tuple[bytes, str]:
    """Build Coach Chris's exact 6-tab .xlsx workbook populated with the challenger's data."""
    pid = int(profile["id"])
    start_iso = str(profile.get("start_date") or "2026-10-19")[:10]
    start_dt = datetime.strptime(start_iso, "%Y-%m-%d").date()
    start_serial = _iso_to_excel_serial(start_iso)

    if selected_week is None:
        today_dt = date.today()
        diff_days = (today_dt - start_dt).days
        selected_week = max(1, min(8, (diff_days // 7) + 1)) if diff_days >= 0 else 1
    else:
        selected_week = max(0, min(12, int(selected_week)))

    # Fetch all real check-ins, activities, workout logs, and weekly submissions for this profile
    demo_sources = ("Garmin Fenix 7", "Garmin Connect (Fenix 7 + Index S2)", "Garmin Connect (Simulated)")
    checkins_by_date = {}
    for r in db.execute(
        "SELECT * FROM daily_checkins WHERE profile_id=? ORDER BY date ASC", (pid,)
    ).fetchall():
        d = dict(r)
        if d.get("sync_source_garmin") in demo_sources:
            continue
        checkins_by_date[str(d["date"])[:10]] = d

    acts_by_date = {}
    for r in db.execute(
        "SELECT * FROM daily_activities WHERE profile_id=? ORDER BY date ASC, id ASC", (pid,)
    ).fetchall():
        a = dict(r)
        gid = str(a.get("garmin_activity_id") or "")
        if gid.startswith(("act-101", "garmin-run-", "garmin-gym-")):
            continue
        acts_by_date.setdefault(str(a["date"])[:10], []).append(a)

    subs_by_week = {}
    try:
        for r in db.execute(
            "SELECT * FROM weekly_submissions WHERE profile_id=?", (pid,)
        ).fetchall():
            s = dict(r)
            subs_by_week[int(s["week_num"])] = s
    except Exception:
        pass

    workout_logs = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM workout_logs WHERE profile_id=? AND weight_reps != '' ORDER BY week_num ASC, id ASC",
            (pid,),
        ).fetchall()
    ]

    template_path = _find_template_path()
    with zipfile.ZipFile(template_path, "r") as zin:
        sst = _SharedStringsTable(zin.read("xl/sharedStrings.xml"))

        # ── 1. Update Sheet 1: Front Sheet (xl/worksheets/sheet1.xml) ──
        s1_raw = zin.read("xl/worksheets/sheet1.xml")
        s1_root = ET.fromstring(s1_raw)
        s1_cells = _index_cells(s1_root)

        client_name = str(profile.get("client_name") or "Ewan t").strip()
        goal = str(profile.get("goal") or "Weight Loss").strip()
        start_w = float(profile.get("start_weight_kg") or 84.0)
        target_w = float(profile.get("target_weight_kg") or 78.3)
        start_bf = float(profile.get("start_body_fat_pct") or 16.0)
        target_bf = float(profile.get("target_body_fat_pct") or 14.0)
        fat_mass = round(start_w / 100.0 * start_bf, 4)
        lean_mass = round(start_w - fat_mass, 4)
        to_lose = round(target_w - start_w, 4)

        raw_cals = (lean_mass * 2.2) * 14.0
        prot_g = float(profile.get("target_protein_g") or 150)
        prot_kcal = prot_g * 4.0
        fats_g = (raw_cals * 0.3) / 9.0
        fats_kcal = fats_g * 9.0
        carbs_g = (raw_cals - (prot_kcal + fats_kcal)) / 4.0
        water_l = (start_w * 2.2) * 0.67 / 33.814

        _set_cell_string(s1_cells["C9"], client_name, sst)
        _set_cell_string(s1_cells["D9"], goal, sst)
        _set_cell_number(s1_cells["E9"], start_serial, keep_formula=False)
        _set_cell_number(s1_cells["F9"], start_w, keep_formula=False)
        _set_cell_number(s1_cells["G9"], target_w, keep_formula=False)
        _set_cell_number(s1_cells["H9"], start_bf, keep_formula=False)
        _set_cell_number(s1_cells["I9"], target_bf, keep_formula=False)
        _set_cell_formula_cached(s1_cells["J9"], start_serial + 56)

        _set_cell_formula_cached(s1_cells["E12"], lean_mass)
        _set_cell_formula_cached(s1_cells["F12"], fat_mass)
        _set_cell_formula_cached(s1_cells["H12"], to_lose)

        wk_cols = ["C", "D", "E", "F", "G", "H", "I", "J"]
        comp_w = start_w
        for idx, col in enumerate(wk_cols):
            wk_serial = start_serial + idx * 7
            if idx > 0:
                comp_w = comp_w * 0.99
            _set_cell_number(s1_cells[f"{col}16"], wk_serial, keep_formula=(idx in (0, 1)))
            _set_cell_number(s1_cells[f"{col}17"], round(comp_w, 6), keep_formula=(idx in (0, 1)))

        _set_cell_formula_cached(s1_cells["E21"], raw_cals)
        _set_cell_number(s1_cells["F21"], prot_g, keep_formula=False)
        _set_cell_formula_cached(s1_cells["G21"], fats_g)
        _set_cell_formula_cached(s1_cells["H21"], carbs_g)
        _set_cell_formula_cached(s1_cells["L21"], prot_kcal)
        _set_cell_formula_cached(s1_cells["E24"], water_l)
        _set_cell_formula_cached(s1_cells["L25"], fats_kcal)

        try:
            wk_targets = json.loads(profile.get("weekly_targets_json") or "[]")
        except Exception:
            wk_targets = []
        for idx in range(8):
            row_n = 28 + idx
            step_t = (
                int(wk_targets[idx].get("steps"))
                if idx < len(wk_targets) and wk_targets[idx].get("steps")
                else (10000 + idx * 1000)
            )
            _set_cell_number(s1_cells[f"D{row_n}"], step_t, keep_formula=False)

        s1_out = _splice_sheet_data(s1_raw, s1_root)

        # ── 2. Update Sheet 2: CHECK IN SINGLE PRINT (xl/worksheets/sheet2.xml) ──
        s2_raw = zin.read("xl/worksheets/sheet2.xml")
        s2_root = ET.fromstring(s2_raw)
        s2_cells = _index_cells(s2_root)

        print_wk = selected_week if selected_week >= 1 else 1
        print_step_target = (
            int(wk_targets[print_wk - 1].get("steps"))
            if 1 <= print_wk <= len(wk_targets) and wk_targets[print_wk - 1].get("steps")
            else (10000 + max(0, print_wk - 1) * 1000)
        )
        targets_banner = (
            f"{int(round(float(profile.get('target_calories') or raw_cals))):,} kcal | "
            f"{int(prot_g)}g Protein | {print_step_target:,} Steps | "
            f"{float(profile.get('target_water_l') or round(water_l, 2)):.2f}L Water"
        )
        _set_cell_string(s2_cells["G7"], client_name, sst)
        _set_cell_string(s2_cells["G8"], targets_banner, sst)
        wk_header_str = "PRE-COACHING WEEK" if selected_week == 0 else f"WEEK  {selected_week}  of 8"
        _set_cell_string(s2_cells["B10"], wk_header_str, sst)

        wk_offset_days = -7 if selected_week == 0 else (selected_week - 1) * 7
        wk_sub_comment = str((subs_by_week.get(selected_week) or {}).get("challenger_comments") or "").strip()
        day_letters = ["M", "T", "W", "T", "F", "S", "S"]

        for d_idx in range(7):
            r_num = 12 + d_idx
            d_dt = start_dt + timedelta(days=wk_offset_days + d_idx)
            d_iso = d_dt.strftime("%Y-%m-%d")
            d_serial = _iso_to_excel_serial(d_iso)
            c_row = checkins_by_date.get(d_iso, {})
            d_acts = acts_by_date.get(d_iso, [])
            has_data = _has_meaningful_day_data(c_row, d_acts)

            _set_cell_number(s2_cells[f"B{r_num}"], d_serial, keep_formula=False)
            _set_cell_string(s2_cells[f"C{r_num}"], day_letters[d_idx], sst, keep_formula=(r_num == 17))

            wt = c_row.get("weight_kg")
            _set_cell_number(
                s2_cells[f"D{r_num}"],
                float(wt) if (wt is not None and float(wt) > 0) else None,
                keep_formula=False,
            )
            t_serial = _time_to_excel_serial(c_row.get("weigh_time") or ("06:30" if wt else ""))
            _set_cell_number(s2_cells[f"E{r_num}"], t_serial if has_data else None, keep_formula=False)
            _set_cell_string(
                s2_cells[f"F{r_num}"],
                _normalize_training_type_for_chris(c_row.get("training_type")) if has_data else "",
                sst,
            )
            steps_v = int(c_row.get("steps") or 0)
            _set_cell_number(s2_cells[f"G{r_num}"], steps_v if steps_v > 0 else None, keep_formula=False)
            prot_v = int(c_row.get("protein_g") or 0)
            _set_cell_number(s2_cells[f"H{r_num}"], prot_v if prot_v > 0 else None, keep_formula=False)
            cals_v = int(c_row.get("calories") or 0)
            _set_cell_number(s2_cells[f"I{r_num}"], cals_v if cals_v > 0 else None, keep_formula=False)
            sleep_txt = _format_sleep_for_chris(c_row.get("sleep_str"), c_row.get("sleep_mins"))
            _set_cell_string(s2_cells[f"J{r_num}"], sleep_txt if has_data else "", sst)
            stick_txt = str(c_row.get("stick_to_plan") or "Y").strip().upper() if has_data else ""
            if stick_txt not in ("Y", "N"):
                stick_txt = "Y" if has_data else ""
            _set_cell_string(s2_cells[f"K{r_num}"], stick_txt, sst)
            day_note = _build_day_notes(c_row, d_acts)
            _set_cell_string(s2_cells[f"L{r_num}"], day_note, sst)

        if wk_sub_comment and "B20" in s2_cells:
            _set_cell_string(s2_cells["B20"], f"Check-In Notes: {wk_sub_comment}", sst)

        s2_out = _splice_sheet_data(s2_raw, s2_root)

        # ── 3. Update Sheet 3: CHECK IN Comp Based (xl/worksheets/sheet3.xml) ──
        s3_raw = zin.read("xl/worksheets/sheet3.xml")
        s3_root = ET.fromstring(s3_raw)
        s3_cells = _index_cells(s3_root)

        prev_wk_avg_weight = None
        for w in range(1, 13):
            base_row = 12 + w * 10  # Wk 1 = 22, Wk 2 = 32, ..., Wk 12 = 132
            wk_cals = []
            wk_steps = []
            wk_weights = []
            wk_comment = str((subs_by_week.get(w) or {}).get("challenger_comments") or "").strip()

            for d_idx in range(7):
                r_num = base_row + d_idx
                d_dt = start_dt + timedelta(days=(w - 1) * 7 + d_idx)
                d_iso = d_dt.strftime("%Y-%m-%d")
                d_serial = _iso_to_excel_serial(d_iso)
                c_row = checkins_by_date.get(d_iso, {})
                d_acts = acts_by_date.get(d_iso, [])
                has_data = _has_meaningful_day_data(c_row, d_acts)

                # Update Date serial & Day letter while keeping Chris's formulas
                if f"B{r_num}" in s3_cells:
                    _set_cell_number(s3_cells[f"B{r_num}"], d_serial, keep_formula=True)
                if f"C{r_num}" in s3_cells:
                    _set_cell_formula_cached(
                        s3_cells[f"C{r_num}"], day_letters[d_idx], is_string=True, sst=sst
                    ) if s3_cells[f"C{r_num}"].find("s:f", NS) is not None else _set_cell_string(
                        s3_cells[f"C{r_num}"], day_letters[d_idx], sst
                    )

                wt = c_row.get("weight_kg")
                wt_num = float(wt) if (wt is not None and float(wt) > 0) else None
                if wt_num is not None:
                    wk_weights.append(wt_num)
                _set_cell_number(s3_cells[f"D{r_num}"], wt_num, keep_formula=False)

                t_serial = _time_to_excel_serial(c_row.get("weigh_time") or ("06:30" if wt_num else ""))
                _set_cell_number(s3_cells[f"E{r_num}"], t_serial if has_data else None, keep_formula=False)

                _set_cell_string(
                    s3_cells[f"F{r_num}"],
                    _normalize_training_type_for_chris(c_row.get("training_type")) if has_data else "",
                    sst,
                )

                steps_v = int(c_row.get("steps") or 0)
                if steps_v > 0:
                    wk_steps.append(steps_v)
                _set_cell_number(s3_cells[f"G{r_num}"], steps_v if steps_v > 0 else None, keep_formula=False)

                prot_v = int(c_row.get("protein_g") or 0)
                _set_cell_number(s3_cells[f"H{r_num}"], prot_v if prot_v > 0 else None, keep_formula=False)

                cals_v = int(c_row.get("calories") or 0)
                if cals_v > 0:
                    wk_cals.append(cals_v)
                _set_cell_number(s3_cells[f"I{r_num}"], cals_v if cals_v > 0 else None, keep_formula=False)

                sleep_txt = _format_sleep_for_chris(c_row.get("sleep_str"), c_row.get("sleep_mins"))
                _set_cell_string(s3_cells[f"J{r_num}"], sleep_txt if has_data else "", sst)

                stick_txt = str(c_row.get("stick_to_plan") or "Y").strip().upper() if has_data else ""
                if stick_txt not in ("Y", "N"):
                    stick_txt = "Y" if has_data else ""
                _set_cell_string(s3_cells[f"K{r_num}"], stick_txt, sst)

                extra_friday_note = ""
                if d_idx == 4 and wk_comment:
                    extra_friday_note = f"Check-In Summary: {wk_comment.replace(chr(10), ' ')}"
                day_note = _build_day_notes(c_row, d_acts, extra_friday_note)
                _set_cell_string(s3_cells[f"L{r_num}"], day_note, sst)

            # Update Column M cached weekly averages so Excel/QuickLook/Sheets show live numbers
            avg_cals = round(sum(wk_cals) / len(wk_cals), 6) if wk_cals else 0
            avg_steps = round(sum(wk_steps) / len(wk_steps), 6) if wk_steps else 0
            avg_wt = round(sum(wk_weights) / len(wk_weights), 6) if wk_weights else 0

            if f"M{base_row}" in s3_cells:
                _set_cell_formula_cached(s3_cells[f"M{base_row}"], avg_cals)
            if f"M{base_row + 2}" in s3_cells:
                _set_cell_formula_cached(s3_cells[f"M{base_row + 2}"], avg_steps)
            if f"M{base_row + 4}" in s3_cells:
                _set_cell_formula_cached(s3_cells[f"M{base_row + 4}"], avg_wt)

            loss_cell = s3_cells.get(f"M{base_row + 6}")
            if loss_cell is not None:
                if w == 1:
                    d22_wt = checkins_by_date.get(start_iso, {}).get("weight_kg")
                    if avg_wt > 0 and d22_wt:
                        _set_cell_formula_cached(loss_cell, round(1.0 - (float(d22_wt) / avg_wt), 8))
                    else:
                        _set_cell_formula_cached(loss_cell, "#DIV/0!")
                else:
                    if avg_wt > 0 and prev_wk_avg_weight and prev_wk_avg_weight > 0:
                        _set_cell_formula_cached(loss_cell, round(1.0 - (prev_wk_avg_weight / avg_wt), 8))
                    else:
                        _set_cell_formula_cached(loss_cell, "#DIV/0!")
            prev_wk_avg_weight = avg_wt if avg_wt > 0 else None

        s3_out = _splice_sheet_data(s3_raw, s3_root)

        # ── 4. Update Sheet 4 (Mens Workouts) & Sheet 5 (Ladies Workouts) ──
        s4_raw = zin.read("xl/worksheets/sheet4.xml")
        s4_root = ET.fromstring(s4_raw)
        s4_cells = _index_cells(s4_root)

        s5_raw = zin.read("xl/worksheets/sheet5.xml")
        s5_root = ET.fromstring(s5_raw)
        s5_cells = _index_cells(s5_root)

        # Clear template placeholder/example strings in H..O on all non-header workout rows first
        mens_header_rows = {11, 36, 56, 75}
        ladies_header_rows = {11, 30, 47, 70}
        for rn in range(12, 91):
            for col in "HIJKLMNO":
                if rn not in mens_header_rows and f"{col}{rn}" in s4_cells:
                    _set_cell_Blank(s4_cells[f"{col}{rn}"])
                if rn not in ladies_header_rows and f"{col}{rn}" in s5_cells:
                    _set_cell_Blank(s5_cells[f"{col}{rn}"])

        for wl in workout_logs:
            wk_n = int(wl.get("week_num") or 1)
            if not (1 <= wk_n <= 8):
                continue
            col_let = chr(ord("H") + wk_n - 1)
            rk = str(wl.get("row_key") or "").strip()
            w_reps = str(wl.get("weight_reps") or "").strip()
            if not w_reps:
                continue
            track = str(wl.get("track") or "mens").lower()
            if track == "ladies" or rk.startswith("LW"):
                excel_r = LADIES_ROW_KEY_TO_EXCEL_ROW.get(rk)
                if excel_r and f"{col_let}{excel_r}" in s5_cells:
                    _set_cell_string(s5_cells[f"{col_let}{excel_r}"], w_reps, sst)
            else:
                excel_r = MENS_ROW_KEY_TO_EXCEL_ROW.get(rk)
                if excel_r and f"{col_let}{excel_r}" in s4_cells:
                    _set_cell_string(s4_cells[f"{col_let}{excel_r}"], w_reps, sst)

        s4_out = _splice_sheet_data(s4_raw, s4_root)
        s5_out = _splice_sheet_data(s5_raw, s5_root)
        sst_out = sst.to_xml_bytes()

        # ── 5. Repackage into a valid .xlsx zip archive ──
        out_buf = io.BytesIO()
        with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                fname = item.filename
                if fname == "xl/calcChain.xml":
                    # Omit calcChain.xml so Excel rebuilds formula dependency chain cleanly on open
                    continue
                raw_data = zin.read(fname)
                if fname == "xl/sharedStrings.xml":
                    raw_data = sst_out
                elif fname == "xl/worksheets/sheet1.xml":
                    raw_data = s1_out
                elif fname == "xl/worksheets/sheet2.xml":
                    raw_data = s2_out
                elif fname == "xl/worksheets/sheet3.xml":
                    raw_data = s3_out
                elif fname == "xl/worksheets/sheet4.xml":
                    raw_data = s4_out
                elif fname == "xl/worksheets/sheet5.xml":
                    raw_data = s5_out
                elif fname == "xl/_rels/workbook.xml.rels":
                    txt = raw_data.decode("utf-8")
                    txt = re.sub(r'<Relationship\b[^>]*Target="calcChain\.xml"[^>]*/>', "", txt)
                    raw_data = txt.encode("utf-8")
                elif fname == "[Content_Types].xml":
                    txt = raw_data.decode("utf-8")
                    txt = re.sub(r'<Override\b[^>]*PartName="/xl/calcChain\.xml"[^>]*/>', "", txt)
                    raw_data = txt.encode("utf-8")
                zout.writestr(item, raw_data)

    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", client_name).strip("_") or "Challenger"
    filename = f"{safe_name}_CS_Fitness_Week_{selected_week}_CheckIn.xlsx"
    return out_buf.getvalue(), filename


def _read_cell_val(cell_el, strings: list):
    if cell_el is None:
        return None
    v_el = cell_el.find("s:v", NS)
    if v_el is None or v_el.text is None:
        inline_t = cell_el.find(".//s:is/s:t", NS)
        return inline_t.text if inline_t is not None else None
    t_attr = cell_el.attrib.get("t", "")
    raw = v_el.text
    if t_attr == "s":
        try:
            return strings[int(raw)]
        except Exception:
            return raw
    if t_attr == "e":
        return None
    return raw


def import_chris_excel_bytes(
    db,
    xlsx_bytes: bytes,
    profile: dict,
    upsert_checkin_fn,
    workout_templates: dict,
) -> dict:
    """Import daily check-ins and workout logs from a Coach Chris .xlsx spreadsheet."""
    pid = int(profile["id"])
    start_iso = str(profile.get("start_date") or "2026-10-19")[:10]
    start_dt = datetime.strptime(start_iso, "%Y-%m-%d").date()

    with zipfile.ZipFile(io.BytesIO(xlsx_bytes), "r") as zin:
        strings = []
        if "xl/sharedStrings.xml" in zin.namelist():
            sst_root = ET.fromstring(zin.read("xl/sharedStrings.xml"))
            strings = [
                "".join(t.text or "" for t in si.findall(".//s:t", NS))
                for si in sst_root.findall("s:si", NS)
            ]

        imported_dates = []
        # 1. Parse Sheet 3: CHECK IN Comp Based (Weeks 1..12, rows 22..138)
        if "xl/worksheets/sheet3.xml" in zin.namelist():
            s3_root = ET.fromstring(zin.read("xl/worksheets/sheet3.xml"))
            s3_cells = _index_cells(s3_root)
            for w in range(1, 13):
                base_row = 12 + w * 10
                for d_idx in range(7):
                    r_num = base_row + d_idx
                    # Ignore the template's stray example row G23=11000, K23=Y if no weight/cals/prot/sleep/notes
                    b_val = _read_cell_val(s3_cells.get(f"B{r_num}"), strings)
                    d_iso = _excel_serial_to_iso(b_val) or (
                        start_dt + timedelta(days=(w - 1) * 7 + d_idx)
                    ).strftime("%Y-%m-%d")

                    wt_raw = _read_cell_val(s3_cells.get(f"D{r_num}"), strings)
                    time_raw = _read_cell_val(s3_cells.get(f"E{r_num}"), strings)
                    type_raw = _read_cell_val(s3_cells.get(f"F{r_num}"), strings)
                    steps_raw = _read_cell_val(s3_cells.get(f"G{r_num}"), strings)
                    prot_raw = _read_cell_val(s3_cells.get(f"H{r_num}"), strings)
                    cals_raw = _read_cell_val(s3_cells.get(f"I{r_num}"), strings)
                    sleep_raw = _read_cell_val(s3_cells.get(f"J{r_num}"), strings)
                    stick_raw = _read_cell_val(s3_cells.get(f"K{r_num}"), strings)
                    notes_raw = _read_cell_val(s3_cells.get(f"L{r_num}"), strings)

                    # Skip untouched template placeholder in row 23 (G23=11000, K23='Y', everything else empty)
                    if (
                        r_num == 23
                        and str(steps_raw or "") == "11000"
                        and not any([wt_raw, prot_raw, cals_raw, sleep_raw, notes_raw])
                    ):
                        continue

                    payload = {}
                    if wt_raw is not None and str(wt_raw).strip() != "":
                        try:
                            payload["weight_kg"] = round(float(wt_raw), 2)
                        except Exception:
                            pass
                    if time_raw is not None and str(time_raw).strip() != "":
                        payload["weigh_time"] = _excel_serial_to_time_str(time_raw)
                    if type_raw is not None and str(type_raw).strip() != "":
                        payload["training_type"] = _normalize_training_type_for_chris(str(type_raw))
                    if steps_raw is not None and str(steps_raw).strip() != "":
                        try:
                            st = int(round(float(steps_raw)))
                            if st > 0:
                                payload["steps"] = st
                        except Exception:
                            pass
                    if prot_raw is not None and str(prot_raw).strip() != "":
                        try:
                            pr = int(round(float(prot_raw)))
                            if pr > 0:
                                payload["protein_g"] = pr
                        except Exception:
                            pass
                    if cals_raw is not None and str(cals_raw).strip() != "":
                        try:
                            ca = int(round(float(cals_raw)))
                            if ca > 0:
                                payload["calories"] = ca
                        except Exception:
                            pass
                    if sleep_raw is not None and str(sleep_raw).strip() != "":
                        payload["sleep_str"] = str(sleep_raw).strip()
                    if stick_raw is not None and str(stick_raw).strip().upper() in ("Y", "N"):
                        payload["stick_to_plan"] = str(stick_raw).strip().upper()
                    if notes_raw is not None and str(notes_raw).strip() != "":
                        payload["notes"] = str(notes_raw).strip()

                    has_real = any(
                        k in payload
                        for k in ("weight_kg", "steps", "protein_g", "calories", "sleep_str", "notes")
                    )
                    if has_real:
                        upsert_checkin_fn(db, d_iso, payload, pid)
                        imported_dates.append(d_iso)

        # 2. Parse Sheet 4 (Mens Workouts) & Sheet 5 (Ladies Workouts)
        template_meta = {}
        for trk, wlist in (workout_templates or {}).items():
            for wobj in wlist:
                wnum = int(wobj["workout_num"])
                for row_meta in wobj.get("rows", []):
                    template_meta[row_meta["row_key"]] = (trk, wnum, row_meta)

        template_examples = {
            "Insert weights & reps",
            "here. Example below",
            "40kg x9",
            "50kg x6",
            "60kg x4, 4",
            "40kg x15",
            "60kg x8",
            "70kg x5",
            "80kg x3, 3",
            "40kg x10, 10, 10",
            "20kg x10, 10",
            "30kg x6, 6",
            "16kg x 10, 10, 10, 10",
            "16kg x12, 12, 12",
            "14kg x 12,12,10",
            "10kg x 12,12,12",
        }
        imported_workouts = 0
        for spath, row_map in (
            ("xl/worksheets/sheet4.xml", MENS_EXCEL_ROW_TO_KEY),
            ("xl/worksheets/sheet5.xml", LADIES_EXCEL_ROW_TO_KEY),
        ):
            if spath not in zin.namelist():
                continue
            s_root = ET.fromstring(zin.read(spath))
            s_cells = _index_cells(s_root)
            for excel_r, rk in row_map.items():
                if rk not in template_meta:
                    continue
                trk, wnum, rmeta = template_meta[rk]
                for wk_n in range(1, 9):
                    col_let = chr(ord("H") + wk_n - 1)
                    val = _read_cell_val(s_cells.get(f"{col_let}{excel_r}"), strings)
                    txt = str(val or "").strip()
                    if not txt or (wk_n == 1 and txt in template_examples):
                        continue
                    existing = db.execute(
                        "SELECT id FROM workout_logs WHERE profile_id=? AND row_key=? AND week_num=?",
                        (pid, rk, wk_n),
                    ).fetchone()
                    if existing:
                        db.execute(
                            "UPDATE workout_logs SET weight_reps=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                            (txt, existing["id"]),
                        )
                    else:
                        db.execute(
                            """INSERT INTO workout_logs
                               (profile_id, track, workout_num, row_key, exercise_order, exercise_name, exercise_notes, target_sets, target_reps, rest_secs, week_num, weight_reps, logged_date)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                pid,
                                trk,
                                wnum,
                                rk,
                                rmeta.get("order", "A"),
                                rmeta.get("exercise", ""),
                                rmeta.get("notes", ""),
                                int(rmeta.get("sets") or 1),
                                str(rmeta.get("reps") or ""),
                                int(rmeta.get("rest") or 60),
                                wk_n,
                                txt,
                                date.today().strftime("%Y-%m-%d"),
                            ),
                        )
                    imported_workouts += 1
        db.commit()

    return {
        "ok": True,
        "imported_days": len(imported_dates),
        "dates": sorted(set(imported_dates)),
        "imported_workouts": imported_workouts,
    }


def normalize_image_bytes_to_jpeg_data_url(
    raw_bytes: bytes,
    filename: str = "",
    mime_type: str = "",
    max_dim: int = 900,
    quality: int = 82,
) -> str:
    """Convert any image bytes (including iPhone .HEIC / .HEIF, PNG, WebP, JPEG) into a resized JPEG data URL."""
    if not raw_bytes:
        raise ValueError("Empty image file")

    # 1. Try Pillow (+ pillow-heif if installed)
    try:
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except Exception:
            pass
        from PIL import Image, ImageOps

        im = Image.open(io.BytesIO(raw_bytes))
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            bg = Image.new("RGB", im.size, (10, 14, 11))
            if "A" in im.getbands():
                bg.paste(im, mask=im.split()[-1])
            else:
                bg.paste(im.convert("RGB"))
            im = bg
        elif im.mode == "L":
            im = im.convert("RGB")
        w, h = im.size
        if max(w, h) > max_dim:
            scale = max_dim / float(max(w, h))
            im = im.resize((max(1, int(round(w * scale))), max(1, int(round(h * scale)))), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=quality, optimize=True)
        b64 = base64.b64encode(out.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception:
        pass

    # 2. Fallback on macOS: built-in /usr/bin/sips (natively decodes Apple .HEIC / .HEIF)
    sips_bin = shutil.which("sips")
    if sips_bin:
        ext = os.path.splitext(filename or "")[1].lower() or ".heic"
        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = os.path.join(tmpdir, f"input{ext}")
            out_path = os.path.join(tmpdir, "output.jpg")
            with open(in_path, "wb") as f:
                f.write(raw_bytes)
            cmd = [
                sips_bin,
                "-s",
                "format",
                "jpeg",
                "-s",
                "formatOptions",
                str(quality),
                "-Z",
                str(max_dim),
                in_path,
                "--out",
                out_path,
            ]
            res = subprocess.run(cmd, capture_output=True, timeout=15)
            if res.returncode == 0 and os.path.exists(out_path):
                with open(out_path, "rb") as f:
                    jpg_bytes = f.read()
                if jpg_bytes:
                    b64 = base64.b64encode(jpg_bytes).decode("ascii")
                    return f"data:image/jpeg;base64,{b64}"

    # 3. If already a standard web image (JPEG/PNG/WebP), return as-is data URL
    header = raw_bytes[:16]
    if header.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif header.startswith(b"\x89PNG"):
        mime = "image/png"
    elif header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise ValueError("Unsupported or unreadable HEIC/image format on server")
    b64 = base64.b64encode(raw_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


def normalize_image_data_url(data_url: str, max_dim: int = 900, quality: int = 82) -> str:
    """Ensure a data:image/... URL is browser-displayable JPEG/PNG (converting data:image/heic if needed)."""
    s = str(data_url or "").strip()
    if not s or not s.startswith("data:"):
        return s
    m = re.match(r"^data:([^;,]+)?(?:;charset=[^;,]+)?;base64,(.+)$", s, re.DOTALL | re.IGNORECASE)
    if not m:
        return s
    mime = (m.group(1) or "").lower()
    b64_part = m.group(2)
    try:
        raw_bytes = base64.b64decode(b64_part)
    except Exception:
        return s
    is_heic_bytes = len(raw_bytes) > 12 and raw_bytes[4:8] == b"ftyp" and raw_bytes[8:12] in (
        b"heic",
        b"heix",
        b"hevc",
        b"hevx",
        b"mif1",
        b"msf1",
    )
    if "heic" in mime or "heif" in mime or "octet-stream" in mime or is_heic_bytes:
        try:
            return normalize_image_bytes_to_jpeg_data_url(
                raw_bytes, filename="upload.heic", mime_type=mime, max_dim=max_dim, quality=quality
            )
        except Exception:
            return s
    return s
