import sqlite3
import os
from flask import g, current_app


_TV_SESSIONS_SYNCED = set()


def get_db():
    if "db" not in g:
        path = current_app.config.get("DATABASE") or current_app.config["DATABASE_PATH"]
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except OSError:
            fallback_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
            os.makedirs(fallback_dir, exist_ok=True)
            path = os.path.join(fallback_dir, "gym.db")
        g.db = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
        has_tables = g.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='challenge_profiles'"
        ).fetchone()
        if not has_tables:
            init_db()
            try:
                from challenge_blocks import ensure_blocks_and_auth_tables
                ensure_blocks_and_auth_tables(g.db)
            except Exception:
                pass
        elif not current_app.config.get("TESTING") and path not in _TV_SESSIONS_SYNCED:
            try:
                seed_default_tv_sessions(g.db)
                g.db.commit()
                _TV_SESSIONS_SYNCED.add(path)
            except Exception:
                pass
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            coach_notes  TEXT NOT NULL DEFAULT '',
            session_type TEXT NOT NULL DEFAULT 'strength',
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS blocks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            label      TEXT NOT NULL,
            focus      TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS exercises (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            block_id   INTEGER NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
            code       TEXT NOT NULL DEFAULT '',
            name       TEXT NOT NULL,
            sets_reps  TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS schedule (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            day_of_week INTEGER NOT NULL,
            start_time  TEXT NOT NULL,
            session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            UNIQUE(day_of_week, start_time)
        );

        CREATE TABLE IF NOT EXISTS override (
            id         INTEGER PRIMARY KEY CHECK (id = 1),
            session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
            set_at     TIMESTAMP
        );

        INSERT OR IGNORE INTO override (id, session_id) VALUES (1, NULL);

        CREATE TABLE IF NOT EXISTS calendar (
            date       TEXT PRIMARY KEY,
            session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL
        );
    """)
    # Migrations for existing databases
    for stmt in [
        "ALTER TABLE sessions ADD COLUMN session_type TEXT NOT NULL DEFAULT 'strength'",
    ]:
        try:
            db.execute(stmt)
        except Exception:
            pass

    init_challenge_tables(db)
    try:
        if not current_app.config.get("TESTING"):
            seed_default_tv_sessions(db)
    except Exception:
        pass
    db.commit()


def seed_default_tv_sessions(db):
    """Auto-seed CS Performance TV workouts, calendar dates, and default weekly schedule on cloud/local startup."""
    import json as _json
    import_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "data", "cs_performance_import.json")
    )
    if os.path.exists(import_path):
        with open(import_path, "r", encoding="utf-8") as f:
            sessions_data = _json.load(f)
        for s in sessions_data:
            name = (s.get("name") or "").strip()
            if not name:
                continue
            existing = db.execute("SELECT id FROM sessions WHERE name=?", (name,)).fetchone()
            if existing:
                sid = existing["id"]
            else:
                cur = db.execute(
                    "INSERT INTO sessions (name, coach_notes, session_type) VALUES (?,?,?)",
                    (name, s.get("coach_notes", ""), s.get("session_type", "strength")),
                )
                sid = cur.lastrowid
                for i, block in enumerate(s.get("blocks", [])):
                    bcur = db.execute(
                        "INSERT INTO blocks (session_id, label, focus, sort_order) VALUES (?,?,?,?)",
                        (sid, block.get("label", ""), block.get("focus", ""), i),
                    )
                    bid = bcur.lastrowid
                    for j, ex in enumerate(block.get("exercises", [])):
                        db.execute(
                            "INSERT INTO exercises (block_id, code, name, sets_reps, sort_order) VALUES (?,?,?,?,?)",
                            (bid, ex.get("code", ""), ex.get("name", ""), ex.get("sets_reps", ""), j),
                        )
            cal_date = (s.get("calendar_date") or "").strip()
            if cal_date and sid:
                db.execute(
                    "INSERT OR IGNORE INTO calendar (date, session_id) VALUES (?, ?)",
                    (cal_date, sid),
                )

    sched_count = db.execute("SELECT COUNT(*) as c FROM schedule").fetchone()
    if sched_count and sched_count["c"] == 0:
        rows = db.execute("SELECT id, name FROM sessions ORDER BY id").fetchall()
        if rows:
            day_tokens = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            for dow, token in enumerate(day_tokens):
                matched_id = None
                for r in rows:
                    if f"- {token} " in r["name"] or token.lower() in r["name"].lower():
                        matched_id = r["id"]
                        break
                if matched_id is None:
                    matched_id = rows[dow % len(rows)]["id"]
                db.execute(
                    "INSERT OR IGNORE INTO schedule (day_of_week, start_time, session_id) VALUES (?,?,?)",
                    (dow, "04:00", matched_id),
                )



def calculate_challenge_targets(
    start_weight_kg=84.0,
    target_weight_kg=78.3,
    start_body_fat_pct=16.0,
    target_body_fat_pct=14.0,
    protein_g=150,
    start_date="2026-10-19",
    goal="Weight Loss",
    returning_member=False,
):
    """Calculate exact CS Fitness 8-Week Challenge targets matching Chris's Excel formulas."""
    from datetime import datetime as _dt, timedelta as _td

    start_w = float(start_weight_kg)
    target_w = float(target_weight_kg)
    start_bf = float(start_body_fat_pct)
    target_bf = float(target_body_fat_pct)
    prot_g = int(round(float(protein_g)))

    # Excel Front Sheet:
    # F12 (Fat Mass) = F9 / 100 * H9
    fat_mass_kg = round(start_w / 100.0 * start_bf, 2)
    # E12 (Lean Body Mass) = F9 - F12
    lean_body_mass_kg = round(start_w - fat_mass_kg, 2)
    # H12 (To Lose) = G9 - F9
    to_lose_kg = round(target_w - start_w, 2)

    # E21 (Calories) = (E12 * 2.2) * 14
    raw_calories = (lean_body_mass_kg * 2.2) * 14.0
    calories = int(round(raw_calories))

    # L21 (Protein kcal) = F21 * 4
    protein_kcal = prot_g * 4.0

    # G21 (Fats g) = (E21 * 0.3) / 9
    raw_fats_g = (raw_calories * 0.30) / 9.0
    fats_g = int(round(raw_fats_g))

    # L25 (Fat kcal) = G21 * 9
    fat_kcal = raw_fats_g * 9.0

    # H21 (Carbs g) = (E21 - (L21 + L25)) / 4
    raw_carbs_g = (raw_calories - (protein_kcal + fat_kcal)) / 4.0
    carbs_g = int(round(raw_carbs_g))

    # E24 (Water L) = (F9 * 2.2) * 0.67 / 33.814
    water_l = round((start_w * 2.2) * 0.67 / 33.814, 2)

    try:
        dt_start = _dt.strptime(start_date[:10], "%Y-%m-%d")
    except Exception:
        dt_start = _dt(2026, 10, 19)
    end_date = (dt_start + _td(days=56)).strftime("%Y-%m-%d")

    weekly_targets = []
    curr_w = start_w
    base_steps = 14000 if returning_member else 10000
    for wk in range(1, 9):
        wk_date = (dt_start + _td(days=(wk - 1) * 7)).strftime("%Y-%m-%d")
        if wk > 1:
            curr_w = curr_w / 100.0 * 99.0
        step_target = max(base_steps, 10000 + (wk - 1) * 1000)
        weekly_targets.append({
            "week": wk,
            "start_date": wk_date,
            "target_weight_kg": round(curr_w, 2),
            "raw_target_weight_kg": curr_w,
            "min_steps": step_target,
            "cardio_target": "2 or 3x per week",
            "strength_target": "3x per week",
        })

    return {
        "goal": goal,
        "start_date": dt_start.strftime("%Y-%m-%d"),
        "end_date": end_date,
        "start_weight_kg": round(start_w, 2),
        "target_weight_kg": round(target_w, 2),
        "start_body_fat_pct": round(start_bf, 2),
        "target_body_fat_pct": round(target_bf, 2),
        "lean_body_mass_kg": lean_body_mass_kg,
        "fat_mass_kg": fat_mass_kg,
        "to_lose_kg": to_lose_kg,
        "target_calories": calories,
        "raw_calories": round(raw_calories, 3),
        "target_protein_g": prot_g,
        "protein_kcal": int(round(protein_kcal)),
        "target_fats_g": fats_g,
        "fat_kcal": round(fat_kcal, 2),
        "target_carbs_g": carbs_g,
        "target_fibre_g": 30,
        "target_water_l": water_l,
        "target_sleep_hrs": 8.0,
        "returning_member": bool(returning_member),
        "weekly_targets": weekly_targets,
    }


def init_challenge_tables(db):
    import json

    db.executescript("""
        CREATE TABLE IF NOT EXISTS challenge_profiles (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name         TEXT NOT NULL UNIQUE,
            goal                TEXT NOT NULL DEFAULT 'Weight Loss',
            start_date          TEXT NOT NULL DEFAULT '2026-10-19',
            end_date            TEXT NOT NULL DEFAULT '2026-12-14',
            start_weight_kg     REAL NOT NULL DEFAULT 84.0,
            target_weight_kg    REAL NOT NULL DEFAULT 78.3,
            start_body_fat_pct  REAL NOT NULL DEFAULT 16.0,
            target_body_fat_pct REAL NOT NULL DEFAULT 14.0,
            lean_body_mass_kg   REAL NOT NULL DEFAULT 70.56,
            fat_mass_kg         REAL NOT NULL DEFAULT 13.44,
            to_lose_kg          REAL NOT NULL DEFAULT -5.7,
            target_calories     INTEGER NOT NULL DEFAULT 2173,
            target_protein_g    INTEGER NOT NULL DEFAULT 150,
            target_fats_g       INTEGER NOT NULL DEFAULT 72,
            target_carbs_g      INTEGER NOT NULL DEFAULT 230,
            target_fibre_g      INTEGER NOT NULL DEFAULT 30,
            target_water_l      REAL NOT NULL DEFAULT 3.66,
            target_sleep_hrs    REAL NOT NULL DEFAULT 8.0,
            returning_member    INTEGER NOT NULL DEFAULT 0,
            workout_track       TEXT NOT NULL DEFAULT 'mens',
            weekly_targets_json TEXT NOT NULL DEFAULT '[]',
            username            TEXT NOT NULL DEFAULT '',
            password_hash       TEXT NOT NULL DEFAULT '',
            role                TEXT NOT NULL DEFAULT 'challenger',
            email               TEXT NOT NULL DEFAULT '',
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS daily_checkins (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id            INTEGER NOT NULL DEFAULT 1,
            date                  TEXT NOT NULL,
            weight_kg             REAL,
            weigh_time            TEXT NOT NULL DEFAULT '06:30',
            training_type         TEXT NOT NULL DEFAULT 'REST',
            steps                 INTEGER NOT NULL DEFAULT 0,
            protein_g             INTEGER NOT NULL DEFAULT 0,
            calories              INTEGER NOT NULL DEFAULT 0,
            carbs_g               INTEGER NOT NULL DEFAULT 0,
            fats_g                INTEGER NOT NULL DEFAULT 0,
            fibre_g               INTEGER NOT NULL DEFAULT 0,
            water_l               REAL NOT NULL DEFAULT 0.0,
            sleep_mins            INTEGER NOT NULL DEFAULT 0,
            sleep_str             TEXT NOT NULL DEFAULT '',
            sleep_score           INTEGER,
            body_battery          INTEGER,
            resting_hr            INTEGER,
            stick_to_plan         TEXT NOT NULL DEFAULT 'Y',
            notes                 TEXT NOT NULL DEFAULT '',
            caffeine_cutoff_met   INTEGER NOT NULL DEFAULT 0,
            electrolytes_taken    INTEGER NOT NULL DEFAULT 0,
            morning_steps_banked  INTEGER NOT NULL DEFAULT 0,
            checkpoint_12pm_5k    INTEGER NOT NULL DEFAULT 0,
            checkpoint_5pm_10k    INTEGER NOT NULL DEFAULT 0,
            mindset_win           TEXT NOT NULL DEFAULT '',
            class_attended        TEXT NOT NULL DEFAULT '',
            sync_source_garmin    TEXT NOT NULL DEFAULT '',
            sync_source_nutrition TEXT NOT NULL DEFAULT '',
            updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(profile_id, date)
        );

        CREATE TABLE IF NOT EXISTS workout_logs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id     INTEGER NOT NULL DEFAULT 1,
            track          TEXT NOT NULL DEFAULT 'mens',
            workout_num    INTEGER NOT NULL,
            week_num       INTEGER NOT NULL,
            row_key        TEXT NOT NULL,
            exercise_order TEXT NOT NULL,
            exercise_name  TEXT NOT NULL,
            target_sets    INTEGER NOT NULL DEFAULT 1,
            target_reps    TEXT NOT NULL DEFAULT '',
            weight_reps    TEXT NOT NULL DEFAULT '',
            set_logs_json  TEXT NOT NULL DEFAULT '[]',
            logged_date    TEXT NOT NULL DEFAULT '',
            notes          TEXT NOT NULL DEFAULT '',
            updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(profile_id, track, workout_num, week_num, row_key)
        );

        CREATE TABLE IF NOT EXISTS step_routes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL UNIQUE,
            est_steps     INTEGER NOT NULL,
            duration_mins INTEGER NOT NULL,
            category      TEXT NOT NULL DEFAULT 'Outdoor Loop',
            notes         TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS staple_meals (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            slot      TEXT NOT NULL,
            name      TEXT NOT NULL UNIQUE,
            calories  INTEGER NOT NULL,
            protein_g INTEGER NOT NULL,
            carbs_g   INTEGER NOT NULL,
            fats_g    INTEGER NOT NULL,
            fibre_g   INTEGER NOT NULL DEFAULT 0,
            prep_note TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS sync_integrations (
            id                    INTEGER PRIMARY KEY CHECK (id = 1),
            garmin_email          TEXT NOT NULL DEFAULT '',
            garmin_password_set   INTEGER NOT NULL DEFAULT 0,
            garmin_connected      INTEGER NOT NULL DEFAULT 0,
            garmin_last_sync      TEXT NOT NULL DEFAULT '',
            mfp_username          TEXT NOT NULL DEFAULT '',
            nutrition_provider    TEXT NOT NULL DEFAULT 'myfitnesspal',
            nutrition_connected   INTEGER NOT NULL DEFAULT 0,
            nutrition_last_sync   TEXT NOT NULL DEFAULT '',
            telegram_bot_token    TEXT NOT NULL DEFAULT '',
            telegram_chat_id      TEXT NOT NULL DEFAULT '',
            coach_telegram_handle TEXT NOT NULL DEFAULT 'csfitness_chris',
            coach_whatsapp_phone  TEXT NOT NULL DEFAULT '',
            webhook_token         TEXT NOT NULL DEFAULT 'csfit-ewan-sync-2026'
        );

        CREATE TABLE IF NOT EXISTS progress_photos (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id       INTEGER NOT NULL DEFAULT 1,
            week_num         INTEGER NOT NULL DEFAULT 1,
            pose             TEXT NOT NULL DEFAULT 'Front',
            taken_date       TEXT NOT NULL,
            weight_kg        REAL,
            fasted_confirmed INTEGER NOT NULL DEFAULT 1,
            lighting_note    TEXT NOT NULL DEFAULT 'Bright natural/bathroom light, tripod at waist height',
            photo_data_url   TEXT NOT NULL DEFAULT '',
            notes            TEXT NOT NULL DEFAULT '',
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS whatsapp_posts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            sender          TEXT NOT NULL,
            role            TEXT NOT NULL DEFAULT 'member',
            posted_at       TEXT NOT NULL,
            message         TEXT NOT NULL,
            hashtags_json   TEXT NOT NULL DEFAULT '[]',
            steps_extracted INTEGER,
            category        TEXT NOT NULL DEFAULT 'accountability',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS weekly_rhythm_tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            day_name    TEXT NOT NULL,
            title       TEXT NOT NULL UNIQUE,
            category    TEXT NOT NULL DEFAULT 'Prep',
            description TEXT NOT NULL DEFAULT '',
            completed   INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS daily_activities (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id         INTEGER NOT NULL DEFAULT 1,
            date               TEXT NOT NULL,
            source             TEXT NOT NULL DEFAULT 'Manual',
            garmin_activity_id TEXT NOT NULL DEFAULT '',
            activity_type      TEXT NOT NULL DEFAULT 'strength',
            category           TEXT NOT NULL DEFAULT 'GYM',
            title              TEXT NOT NULL,
            start_time         TEXT NOT NULL DEFAULT '',
            duration_mins      REAL NOT NULL DEFAULT 0,
            distance_km        REAL,
            pace_str           TEXT NOT NULL DEFAULT '',
            avg_hr             INTEGER,
            max_hr             INTEGER,
            calories           INTEGER,
            elevation_m        INTEGER,
            steps              INTEGER,
            notes              TEXT NOT NULL DEFAULT '',
            created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS weekly_submissions (
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
            submitted_at        TEXT NOT NULL DEFAULT '',
            reviewed_at         TEXT NOT NULL DEFAULT '',
            updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(profile_id, week_num)
        );
    """)

    # Seed Ewan's profile if not present
    existing = db.execute("SELECT id FROM challenge_profiles WHERE client_name = ?", ("Ewan t",)).fetchone()
    if not existing:
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
        db.execute(
            """INSERT INTO challenge_profiles (
                client_name, goal, start_date, end_date,
                start_weight_kg, target_weight_kg, start_body_fat_pct, target_body_fat_pct,
                lean_body_mass_kg, fat_mass_kg, to_lose_kg,
                target_calories, target_protein_g, target_fats_g, target_carbs_g,
                target_fibre_g, target_water_l, target_sleep_hrs,
                returning_member, workout_track, weekly_targets_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "Ewan t", calc["goal"], calc["start_date"], calc["end_date"],
                calc["start_weight_kg"], calc["target_weight_kg"],
                calc["start_body_fat_pct"], calc["target_body_fat_pct"],
                calc["lean_body_mass_kg"], calc["fat_mass_kg"], calc["to_lose_kg"],
                calc["target_calories"], calc["target_protein_g"],
                calc["target_fats_g"], calc["target_carbs_g"],
                calc["target_fibre_g"], calc["target_water_l"], calc["target_sleep_hrs"],
                0, "mens", json.dumps(calc["weekly_targets"]),
            ),
        )

    # Seed sync_integrations row
    db.execute("INSERT OR IGNORE INTO sync_integrations (id) VALUES (1)")

    # Seed Step Routes
    routes = [
        ("Helix & Kelpies Loop", 6000, 50, "Evening / Weekend", "Flat scenic canal & Kelpies loop — listen to Chris's podcast episode"),
        ("Morning House Loop (Pre-Work)", 4500, 38, "Morning Bank", "Bank before 8:00am so the 12pm 5,000-step checkpoint is automatic"),
        ("Lunch Split Walk", 3000, 25, "Midday Top-Up", "25-min brisk walk between meetings to stay ahead of the 5pm 10k target"),
        ("Post-Dinner Digest Walk", 2500, 20, "Evening Finisher", "Easy 20-min loop after dinner to close the step ring & aid digestion"),
        ("Gym Warmup + Incline Treadmill", 2000, 18, "Indoor / Gym", "10 min pre-workout + 8 min post-workout incline walk on rainy days"),
        ("Laura's Wed 5:15am Run Club", 5500, 35, "CS Community", "Free Wednesday 5:15am community run club starting from CS Fitness"),
    ]
    for name, steps, mins, cat, notes in routes:
        db.execute(
            "INSERT OR IGNORE INTO step_routes (name, est_steps, duration_mins, category, notes) VALUES (?,?,?,?,?)",
            (name, steps, mins, cat, notes),
        )

    # Seed Staple Meals (Laura's 5-Slot Daily Eating Routine & High-Protein Staples)
    meals = [
        ("Breakfast", "0% Greek Yogurt Bowl + MyProtein Whey + Berries & Honey", 385, 42, 41, 5, 6, "Slot 1 (8:00am) — High protein, fast prep, hits sweet tooth early"),
        ("Breakfast", "3 Whole Eggs + 150g Egg Whites on 2 Slices Sourdough", 460, 38, 36, 17, 4, "Slot 1 Savory — Great after 6:00am CS Fitness class"),
        ("Breakfast", "Overnight Oats (60g Oats, Scoop Whey, Chia, Raspberries)", 430, 36, 52, 8, 9, "Prep 3 jars on Sunday night for Mon-Wed mornings"),
        ("Mid-Morning Snack", "200g Kvarg / Skyr + Apple + 15g Almonds", 265, 24, 24, 8, 4, "Slot 2 (11:00am) — Bridges breakfast to lunch with zero crash"),
        ("Mid-Morning Snack", "Clear Whey Isolate Shake + Banana", 190, 21, 25, 0, 3, "Light & refreshing while banking midday steps"),
        ("Lunch", "200g Chicken Breast Rice Bowl + Roasted Peppers & Nando's Peri Drizzle", 560, 52, 62, 11, 6, "Slot 3 (1:30pm) — Sunday batch-prepped staple container"),
        ("Lunch", "Turkey Mince Burrito Bowl (180g 2% Turkey, Black Beans, Rice, Salsa)", 540, 48, 64, 9, 10, "High fibre (10g) + lean protein to keep afternoon hunger away"),
        ("Lunch", "Tuna Steak / 2 Tins Tuna + Crispy Air-Fryer Potatoes + Side Salad", 495, 46, 54, 9, 6, "Quick WFH lunch when prepped tubs run out on Wednesday"),
        ("Afternoon Snack", "2 Rice Cakes + 100g Cottage Cheese + Sliced Turkey Breast", 210, 26, 18, 3, 2, "Slot 4 (4:30pm) — Pre-evening class fuel"),
        ("Afternoon Snack", "Grenade / Fulfil Protein Bar + Black Coffee (Before 3pm!)", 225, 20, 18, 8, 3, "Grab-and-go emergency staple — keep in gym bag"),
        ("Dinner", "220g 5% Lean Steak Mince Burger Fakeaway + Air-Fryer Wedges + Broccoli", 640, 52, 58, 21, 8, "Slot 5 (7:00pm) — Weekend fakeaway winner that fits macros"),
        ("Dinner", "200g Salmon Fillet + 200g Baby Potatoes + Asparagus & Green Beans", 620, 44, 42, 28, 7, "Omega-3 rich recovery dinner on heavy strength days"),
        ("Dinner", "200g Chicken Stir-Fry + Egg Noodles + Mixed Stir-Fry Veg & Soy Ginger", 545, 49, 63, 10, 7, "12-minute pan meal — high volume, super filling"),
    ]
    for slot, name, cal, p, c, f, fib, note in meals:
        db.execute(
            """INSERT OR IGNORE INTO staple_meals
               (slot, name, calories, protein_g, carbs_g, fats_g, fibre_g, prep_note)
               VALUES (?,?,?,?,?,?,?,?)""",
            (slot, name, cal, p, c, f, fib, note),
        )

    # Seed Weekly Rhythm & Life App tasks
    rhythm = [
        ("Sunday", "Sunday Meal Prep (1.5–2 hrs) + Big Food Shop", "Nutrition Prep", "Cook 2 main proteins (chicken breast + 2% turkey mince), portion carbs & veg so Mon–Wed lunches/dinners are grab-and-go.", 0),
        ("Monday", "Start Check-In (Day 1 Monday): Starting Weight & 3 Baseline Photos", "Check-In", "On Day 1 Monday of the block: log fasted starting weight, measurements & 3 starting photos (Side, Front, Back).", 0),
        ("Wednesday", "Wednesday Mini Food Shop (Fruit, Veg, Yogurt, Lean Meat)", "Nutrition Prep", "Restock fresh berries, Skyr/Kvarg, salad & lean protein so Friday/Saturday fridge isn't empty.", 0),
        ("Friday", "Friday Weekly Check-In (Wk 1 Fri = No Photos · Wk 2–8 Fri = + 3 Photos)", "Check-In", "Check-ins are every Friday! First Friday of Week 1 is weight & review only (no photos). Weeks 2–8 Fridays include 3 progress photos (Side, Front, Back).", 0),
        ("Friday", "Weekend Social & Football Gameplan", "Lifestyle Balance", "Bank 6,000+ steps before midday, high-protein lunch, pick lighter drink choices or zero-cal mixers, log honestly.", 0),
        ("Sunday", "Sunday H2O + Electrolytes Recovery Protocol", "Recovery", "Even if horizontal on Sunday: 3.66L water + electrolytes, hit 150g protein, and get outside for fresh-air steps.", 0),
    ]
    for day_name, title, cat, desc, comp in rhythm:
        db.execute(
            "INSERT OR IGNORE INTO weekly_rhythm_tasks (day_name, title, category, description, completed) VALUES (?,?,?,?,?)",
            (day_name, title, cat, desc, comp),
        )

    # Seed WhatsApp Coaching & Accountability Feed from the Oct 2026 chats
    wa_seed = [
        ("Chris", "coach", "2026-10-10 01:03", "First three videos watch then watch again — Non-negotiables: Steps, Calories, Protein, Water, Sleep. Do the basics relentlessly for 56 days!", '["#nonNegotiables", "#winTheDay"]', None, "announcement"),
        ("Laura (L💫)", "coach", "2026-10-14 06:03", "Hi Everyone! I'll be looking after the food and accountability side of the programme with Chris. Focus on familiarising yourself with hitting cals, protein and hitting steps — NON NEGOTIABLES 🤝", '["#accountability", "#staples"]', None, "announcement"),
        ("Laura (L💫)", "coach", "2026-10-16 02:11", "Kicking things off with check-in sheets 🔢 Complete daily — weight first thing after toilet, log time, steps, protein, calories, sleep & stick to plan (Y/N). Starting photos by Monday morning latest!", '["#checkin", "#photos"]', None, "announcement"),
        ("Laura (L💫)", "coach", "2026-10-16 10:04", "Classes at CS Fitness 💚 Mon/Wed/Fri 6am & Mon/Tue/Thu 6pm Cardio, Tue/Thu 6am & Sat 9am Strength Block, HYROX Fri/Sat/Sun, and free Wed 5:15am Run Club!", '["#classes", "#CSFitness"]', None, "announcement"),
        ("Laura (L💫)", "coach", "2026-10-17 02:38", "Weekly Food Shop Insights 💥 When meals are planned ahead, it's easier to include lean proteins, vegetables, and complex carbohydrates instead of ultra-processed foods. Big shop Sunday + mini top-up Wednesday!", '["#foodshop", "#mealprep"]', None, "announcement"),
    ]
    if db.execute("SELECT COUNT(*) as c FROM whatsapp_posts").fetchone()["c"] == 0:
        for sender, role, posted_at, msg, tags, steps_val, cat in wa_seed:
            db.execute(
                """INSERT INTO whatsapp_posts (sender, role, posted_at, message, hashtags_json, steps_extracted, category)
                   VALUES (?,?,?,?,?,?,?)""",
                (sender, role, posted_at, msg, tags, steps_val, cat),
            )


def init_app(app):
    app.teardown_appcontext(close_db)
