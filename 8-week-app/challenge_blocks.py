from flask import Blueprint, jsonify, render_template, request, redirect, session, url_for
from datetime import datetime, timedelta
import bcrypt
import json
import re
import secrets

from database import get_db, calculate_challenge_targets, init_challenge_tables
from challenge import _get_active_profile, _is_current_user_admin

challenge_blocks_bp = Blueprint("challenge_blocks", __name__)


DEFAULT_ANNUAL_BLOCKS = [
    {
        "block_code": "2026-B4-AUG",
        "name": "Block 4 · Late Summer 8-Week Challenge",
        "pre_coaching_date": "2026-07-27",
        "start_date": "2026-08-03",
        "end_date": "2026-09-28",
        "status": "Completed",
        "invite_code": "CS-AUG2026",
        "gap_note": "2-week recovery & intake gap before Block 5 (Oct)",
    },
    {
        "block_code": "2026-B5-OCT",
        "name": "Block 5 · Autumn/Winter 8-Week Challenge",
        "pre_coaching_date": "2026-10-12",
        "start_date": "2026-10-19",
        "end_date": "2026-12-14",
        "status": "Active",
        "invite_code": "CS-OCT2026",
        "gap_note": "Active cohort · 3-week Christmas/New Year break after 14 Dec",
    },
    {
        "block_code": "2027-B1-JAN",
        "name": "Block 1 · New Year 8-Week Challenge",
        "pre_coaching_date": "2027-01-04",
        "start_date": "2027-01-11",
        "end_date": "2027-03-08",
        "status": "Upcoming",
        "invite_code": "CS-JAN2027",
        "gap_note": "2-week gap before Block 2 (Late March)",
    },
    {
        "block_code": "2027-B2-MAR",
        "name": "Block 2 · Spring 8-Week Challenge",
        "pre_coaching_date": "2027-03-22",
        "start_date": "2027-03-29",
        "end_date": "2027-05-24",
        "status": "Upcoming",
        "invite_code": "CS-MAR2027",
        "gap_note": "2-week gap before Block 3 (June)",
    },
    {
        "block_code": "2027-B3-JUN",
        "name": "Block 3 · Summer 8-Week Challenge",
        "pre_coaching_date": "2027-06-07",
        "start_date": "2027-06-14",
        "end_date": "2027-08-09",
        "status": "Upcoming",
        "invite_code": "CS-JUN2027",
        "gap_note": "2-week summer break before Block 4",
    },
]


def ensure_blocks_and_auth_tables(db):
    init_challenge_tables(db)
    db.execute(
        """CREATE TABLE IF NOT EXISTS challenge_blocks (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            block_code          TEXT NOT NULL UNIQUE,
            name                TEXT NOT NULL,
            pre_coaching_date   TEXT NOT NULL,
            start_date          TEXT NOT NULL,
            end_date            TEXT NOT NULL,
            status              TEXT NOT NULL DEFAULT 'Upcoming',
            invite_code         TEXT NOT NULL UNIQUE,
            gap_note            TEXT NOT NULL DEFAULT '',
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS challenge_block_enrollments (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            block_id            INTEGER NOT NULL,
            profile_id          INTEGER NOT NULL,
            is_returning        INTEGER NOT NULL DEFAULT 0,
            joined_via          TEXT NOT NULL DEFAULT 'Coach Invite',
            payment_ref         TEXT NOT NULL DEFAULT '',
            status              TEXT NOT NULL DEFAULT 'Active',
            enrolled_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(block_id, profile_id)
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS challenge_user_accounts (
            profile_id      INTEGER PRIMARY KEY,
            username        TEXT NOT NULL UNIQUE,
            password_hash   TEXT NOT NULL DEFAULT '',
            role            TEXT NOT NULL DEFAULT 'challenger',
            email           TEXT NOT NULL DEFAULT '',
            invite_token    TEXT NOT NULL DEFAULT '',
            auth_provider   TEXT NOT NULL DEFAULT 'email',
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    for col_sql in (
        "ALTER TABLE challenge_user_accounts ADD COLUMN invite_token TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE challenge_user_accounts ADD COLUMN auth_provider TEXT NOT NULL DEFAULT 'email'",
    ):
        try:
            db.execute(col_sql)
        except Exception:
            pass

    cnt = db.execute("SELECT COUNT(*) AS c FROM challenge_blocks").fetchone()["c"]
    if cnt == 0:
        for b in DEFAULT_ANNUAL_BLOCKS:
            db.execute(
                """INSERT INTO challenge_blocks (
                    block_code, name, pre_coaching_date, start_date, end_date, status, invite_code, gap_note
                ) VALUES (?,?,?,?,?,?,?,?)""",
                (
                    b["block_code"],
                    b["name"],
                    b["pre_coaching_date"],
                    b["start_date"],
                    b["end_date"],
                    b["status"],
                    b["invite_code"],
                    b["gap_note"],
                ),
            )
        active_block = db.execute("SELECT id FROM challenge_blocks WHERE block_code='2026-B5-OCT'").fetchone()
        if active_block:
            for p in db.execute("SELECT id, client_name, returning_member FROM challenge_profiles").fetchall():
                db.execute(
                    """INSERT OR IGNORE INTO challenge_block_enrollments (block_id, profile_id, is_returning, joined_via)
                       VALUES (?,?,?,?)""",
                    (active_block["id"], p["id"], p["returning_member"], "Cohort Seed"),
                )
        db.commit()

    # Purge any legacy sample/demo profiles or simulated demo check-ins
    demo_pids = [
        r["id"]
        for r in db.execute(
            "SELECT id FROM challenge_profiles WHERE client_name LIKE 'Sarah M%' OR client_name LIKE 'Dan K%'"
        ).fetchall()
    ]
    for dpid in demo_pids:
        db.execute("DELETE FROM challenge_block_enrollments WHERE profile_id=?", (dpid,))
        db.execute("DELETE FROM challenge_user_accounts WHERE profile_id=?", (dpid,))
        db.execute("DELETE FROM daily_checkins WHERE profile_id=?", (dpid,))
        db.execute("DELETE FROM challenge_profiles WHERE id=?", (dpid,))
    db.execute(
        """DELETE FROM daily_checkins
           WHERE sync_source_garmin IN ('Garmin Fenix 7', 'Garmin Connect (Fenix 7 + Index S2)', 'Garmin Connect (Simulated)')"""
    )

    # Ensure the 3 Admin accounts (Ewan, Chris, Laura) exist
    admin_seeds = [
        ("Ewan t", "ewan", "taylor.ewan@gmail.com", "mens"),
        ("Chris", "chris", "chris@cs.fitness", "mens"),
        ("Laura", "laura", "laura@cs.fitness", "ladies"),
    ]
    for cname, uname, default_email, track in admin_seeds:
        p_row = db.execute("SELECT id FROM challenge_profiles WHERE LOWER(client_name)=LOWER(?)", (cname,)).fetchone()
        if not p_row:
            calc = calculate_challenge_targets(80.0, 75.0, 16.0, 14.0, 150, "2026-10-19", "Coach / Admin", False)
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
                    cname, "Coach / Admin", "2026-10-19", calc["end_date"],
                    80.0, 75.0, 16.0, 14.0,
                    calc["lean_body_mass_kg"], calc["fat_mass_kg"], calc["to_lose_kg"],
                    calc["target_calories"], calc["target_protein_g"], calc["target_fats_g"], calc["target_carbs_g"],
                    calc["target_fibre_g"], calc["target_water_l"], calc["target_sleep_hrs"],
                    0, track, json.dumps(calc["weekly_targets"]),
                ),
            )
            p_row = db.execute("SELECT id FROM challenge_profiles WHERE LOWER(client_name)=LOWER(?)", (cname,)).fetchone()
        if p_row:
            db.execute(
                """INSERT INTO challenge_user_accounts (profile_id, username, email, role, invite_token)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(profile_id) DO UPDATE SET role='admin',
                       email=CASE WHEN challenge_user_accounts.email='' THEN excluded.email ELSE challenge_user_accounts.email END""",
                (p_row["id"], uname, default_email, "admin", secrets.token_urlsafe(12)),
            )

    # Ensure every profile has a row in challenge_user_accounts
    for p in db.execute("SELECT id, client_name FROM challenge_profiles").fetchall():
        existing = db.execute("SELECT profile_id FROM challenge_user_accounts WHERE profile_id=?", (p["id"],)).fetchone()
        if not existing:
            slug = re.sub(r"[^a-z0-9]", "", p["client_name"].split()[0].lower()) or f"user{p['id']}"
            clash = db.execute("SELECT 1 FROM challenge_user_accounts WHERE username=?", (slug,)).fetchone()
            uname = f"{slug}{p['id']}" if clash else slug
            default_email = "taylor.ewan@gmail.com" if p["client_name"] == "Ewan t" else f"{uname}@taylorfitness.co.uk"
            role = "admin" if p["client_name"].lower() in ("ewan t", "chris", "laura") else "challenger"
            db.execute(
                """INSERT OR IGNORE INTO challenge_user_accounts (profile_id, username, email, role, invite_token)
                   VALUES (?,?,?,?,?)""",
                (p["id"], uname, default_email, role, secrets.token_urlsafe(12)),
            )
    _auto_seed_ewan_backup_if_empty(db)
    db.commit()


def _upsert_challenger_for_block(db, data, block_row):
    cname = (data.get("client_name") or data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    if not cname and email:
        cname = email.split("@")[0].replace(".", " ").title()
    if not cname:
        raise ValueError("Name or email is required")

    returning = bool(data.get("returning_member", False))
    start_w = float(data.get("start_weight_kg") or 80.0)
    target_w = float(data.get("target_weight_kg") or round(start_w * 0.93, 1))
    start_bf = float(data.get("start_body_fat_pct") or 18.0)
    target_bf = float(data.get("target_body_fat_pct") or max(10.0, start_bf - 2.5))
    prot_g = int(data.get("protein_g") or 150)
    track = data.get("workout_track") if data.get("workout_track") in ("mens", "ladies") else "mens"

    calc = calculate_challenge_targets(
        start_weight_kg=start_w,
        target_weight_kg=target_w,
        start_body_fat_pct=start_bf,
        target_body_fat_pct=target_bf,
        protein_g=prot_g,
        start_date=block_row["start_date"],
        goal=data.get("goal", "Weight Loss"),
        returning_member=returning,
    )

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
            weekly_targets_json=excluded.weekly_targets_json""",
        (
            cname,
            calc["goal"],
            calc["start_date"],
            calc["end_date"],
            calc["start_weight_kg"],
            calc["target_weight_kg"],
            calc["start_body_fat_pct"],
            calc["target_body_fat_pct"],
            calc["lean_body_mass_kg"],
            calc["fat_mass_kg"],
            calc["to_lose_kg"],
            calc["target_calories"],
            calc["target_protein_g"],
            calc["target_fats_g"],
            calc["target_carbs_g"],
            30,
            calc["target_water_l"],
            8.0,
            1 if returning else 0,
            track,
            json.dumps(calc["weekly_targets"]),
        ),
    )
    prof = db.execute("SELECT * FROM challenge_profiles WHERE client_name=?", (cname,)).fetchone()
    pid = prof["id"]

    db.execute(
        """INSERT INTO challenge_block_enrollments (block_id, profile_id, is_returning, joined_via, payment_ref)
           VALUES (?,?,?,?,?)
           ON CONFLICT(block_id, profile_id) DO UPDATE SET
               is_returning=excluded.is_returning,
               joined_via=excluded.joined_via,
               payment_ref=CASE WHEN excluded.payment_ref != '' THEN excluded.payment_ref ELSE challenge_block_enrollments.payment_ref END""",
        (
            block_row["id"],
            pid,
            1 if returning else 0,
            data.get("joined_via", "Invite / Signup"),
            str(data.get("payment_ref") or ""),
        ),
    )

    slug = re.sub(r"[^a-z0-9]", "", cname.split()[0].lower()) or f"user{pid}"
    clash = db.execute("SELECT 1 FROM challenge_user_accounts WHERE username=? AND profile_id!=?", (slug, pid)).fetchone()
    uname = f"{slug}{pid}" if clash else slug
    raw_pw = str(data.get("password") or "").strip()
    pw_hash = bcrypt.hashpw(raw_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8") if raw_pw else ""
    invite_token = secrets.token_urlsafe(12)
    is_admin_caller = _is_current_user_admin(db)
    if cname.strip().lower() in ("ewan t", "chris", "laura"):
        role = "admin"
    elif is_admin_caller and data.get("role") in ("challenger", "coach", "admin"):
        role = data.get("role")
    else:
        role = "challenger"

    db.execute(
        """INSERT INTO challenge_user_accounts (profile_id, username, email, password_hash, role, invite_token)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(profile_id) DO UPDATE SET
               email=CASE WHEN excluded.email != '' THEN excluded.email ELSE challenge_user_accounts.email END,
               password_hash=CASE WHEN excluded.password_hash != '' THEN excluded.password_hash ELSE challenge_user_accounts.password_hash END,
               role=excluded.role,
               updated_at=CURRENT_TIMESTAMP""",
        (pid, uname, email or f"{uname}@taylorfitness.co.uk", pw_hash, role, invite_token),
    )
    db.commit()
    acct = db.execute("SELECT * FROM challenge_user_accounts WHERE profile_id=?", (pid,)).fetchone()
    return dict(prof), dict(acct)


@challenge_blocks_bp.route("/challenge/login", methods=["GET"])
def challenge_login_page():
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    blocks = [dict(r) for r in db.execute("SELECT * FROM challenge_blocks ORDER BY start_date").fetchall()]
    is_authed = bool(session.get("challenge_authed") and session.get("challenge_profile_id"))
    active_prof = _get_active_profile(db) if is_authed else None
    return render_template(
        "challenge_login.html",
        blocks=blocks,
        active_profile=active_prof,
        is_authenticated=is_authed,
        invite_code=request.args.get("code", ""),
        invite_token=request.args.get("invite", ""),
        email_prefill=request.args.get("email", ""),
    )


@challenge_blocks_bp.route("/api/challenge/auth/logout", methods=["POST", "GET"])
def api_challenge_auth_logout():
    session.pop("challenge_profile_id", None)
    session.pop("challenge_authed", None)
    if request.method == "GET":
        return redirect(url_for("challenge_blocks.challenge_login_page"))
    return jsonify({"ok": True})


@challenge_blocks_bp.route("/api/challenge/auth/status", methods=["GET"])
def api_challenge_auth_status():
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    prof = _get_active_profile(db)
    acct = db.execute("SELECT * FROM challenge_user_accounts WHERE profile_id=?", (prof["id"],)).fetchone()
    enr = db.execute(
        """SELECT b.* FROM challenge_block_enrollments e
           JOIN challenge_blocks b ON b.id = e.block_id
           WHERE e.profile_id=? ORDER BY b.start_date DESC LIMIT 1""",
        (prof["id"],),
    ).fetchone()
    if not enr:
        enr = db.execute("SELECT * FROM challenge_blocks WHERE status='Active' LIMIT 1").fetchone()
    return jsonify({
        "ok": True,
        "authenticated": bool(session.get("challenge_authed")),
        "profile_id": prof["id"],
        "client_name": prof["client_name"],
        "email": acct["email"] if acct else "",
        "role": acct["role"] if acct else "challenger",
        "has_password": bool(acct and acct["password_hash"]),
        "active_block": dict(enr) if enr else None,
    })


@challenge_blocks_bp.route("/api/challenge/auth/login", methods=["POST"])
def api_challenge_auth_login():
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    data = request.get_json() or {}
    ident = (data.get("email") or data.get("username") or "").strip().lower()
    raw_pw = str(data.get("password") or "").strip()

    acct = db.execute(
        """SELECT a.*, p.client_name FROM challenge_user_accounts a
           JOIN challenge_profiles p ON p.id = a.profile_id
           WHERE LOWER(a.email)=? OR LOWER(a.username)=? OR LOWER(p.client_name)=?""",
        (ident, ident, ident),
    ).fetchone()
    if not acct:
        return jsonify({"ok": False, "error": "Account not found. Check your email/name or use an Invite Code to join."}), 404

    if acct["password_hash"]:
        if not raw_pw or not bcrypt.checkpw(raw_pw.encode("utf-8"), acct["password_hash"].encode("utf-8")):
            return jsonify({"ok": False, "error": "Incorrect password for this account."}), 401
    elif raw_pw:
        # First-time password setup on login if account had no password yet
        pw_hash = bcrypt.hashpw(raw_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        db.execute("UPDATE challenge_user_accounts SET password_hash=?, updated_at=CURRENT_TIMESTAMP WHERE profile_id=?", (pw_hash, acct["profile_id"]))
        db.commit()

    session["challenge_profile_id"] = acct["profile_id"]
    session["challenge_authed"] = True
    return jsonify({
        "ok": True,
        "profile_id": acct["profile_id"],
        "client_name": acct["client_name"],
        "email": acct["email"],
        "role": acct["role"],
    })


@challenge_blocks_bp.route("/api/challenge/auth/set-password", methods=["POST"])
def api_challenge_set_password():
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    data = request.get_json() or {}
    active_prof = _get_active_profile(db)
    pid = int(data.get("profile_id") or active_prof["id"])
    if pid != int(active_prof["id"]) and not _is_current_user_admin(db):
        return jsonify({"ok": False, "error": "Cannot modify another user's password."}), 403
    email = (data.get("email") or "").strip().lower()
    new_pw = str(data.get("new_password") or data.get("password") or "").strip()
    curr_pw = str(data.get("current_password") or "").strip()

    acct = db.execute("SELECT * FROM challenge_user_accounts WHERE profile_id=?", (pid,)).fetchone()
    if acct and acct["password_hash"]:
        if not curr_pw or not bcrypt.checkpw(curr_pw.encode("utf-8"), acct["password_hash"].encode("utf-8")):
            return jsonify({"ok": False, "error": "Current password is required to change an existing password."}), 401

    if len(new_pw) < 4:
        return jsonify({"ok": False, "error": "Password must be at least 4 characters."}), 400

    pw_hash = bcrypt.hashpw(new_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    db.execute(
        """UPDATE challenge_user_accounts
           SET password_hash=?, email=CASE WHEN ? != '' THEN ? ELSE email END, updated_at=CURRENT_TIMESTAMP
           WHERE profile_id=?""",
        (pw_hash, email, email, pid),
    )
    db.commit()
    return jsonify({"ok": True, "profile_id": pid, "message": "Email & password updated!"})


@challenge_blocks_bp.route("/api/challenge/auth/switch-user", methods=["POST"])
def api_challenge_switch_user():
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    data = request.get_json() or {}
    pid = int(data.get("profile_id") or 1)
    raw_pw = str(data.get("password") or "").strip()
    is_admin = _is_current_user_admin(db)

    acct = db.execute("SELECT * FROM challenge_user_accounts WHERE profile_id=?", (pid,)).fetchone()
    if session.get("challenge_profile_id") != pid and not is_admin:
        if acct and acct["password_hash"]:
            if not raw_pw or not bcrypt.checkpw(raw_pw.encode("utf-8"), acct["password_hash"].encode("utf-8")):
                return jsonify({"ok": False, "requires_password": True, "error": "Password required for this challenger profile."}), 401
        else:
            return jsonify({
                "ok": False,
                "error": "Only Coach & Admin accounts can switch between challenger profiles. Please sign in with your own email and password.",
            }), 403

    session["challenge_profile_id"] = pid
    session["challenge_authed"] = True
    prof = _get_active_profile(db, pid)
    return jsonify({"ok": True, "profile": prof, "client_name": prof["client_name"]})


@challenge_blocks_bp.route("/api/challenge/blocks", methods=["GET", "POST"])
def api_challenge_blocks():
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    is_admin = _is_current_user_admin(db)

    if request.method == "POST":
        if not is_admin:
            return jsonify({"ok": False, "error": "Only Coach & Admin accounts can create cohort blocks."}), 403
        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        start_date = (data.get("start_date") or "2027-01-11")[:10]
        if not name:
            return jsonify({"ok": False, "error": "Block name is required"}), 400
        dt_start = datetime.strptime(start_date, "%Y-%m-%d")
        pre_dt = (dt_start - timedelta(days=7)).strftime("%Y-%m-%d")
        end_dt = (dt_start + timedelta(days=56)).strftime("%Y-%m-%d")
        b_code = (data.get("block_code") or f"{dt_start.strftime('%Y')}-B-{dt_start.strftime('%b').upper()}").strip().upper()
        inv_code = (data.get("invite_code") or f"CS-{dt_start.strftime('%b%Y').upper()}").strip().upper()
        status = data.get("status") if data.get("status") in ("Active", "Upcoming", "Completed") else "Upcoming"
        gap_note = (data.get("gap_note") or "8-week cohort block + 1-week pre-coaching").strip()

        if status == "Active":
            db.execute("UPDATE challenge_blocks SET status='Completed' WHERE status='Active' AND start_date < ?", (start_date,))

        db.execute(
            """INSERT INTO challenge_blocks (block_code, name, pre_coaching_date, start_date, end_date, status, invite_code, gap_note)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(block_code) DO UPDATE SET
                   name=excluded.name, pre_coaching_date=excluded.pre_coaching_date,
                   start_date=excluded.start_date, end_date=excluded.end_date,
                   status=excluded.status, invite_code=excluded.invite_code, gap_note=excluded.gap_note""",
            (b_code, name, pre_dt, start_date, end_dt, status, inv_code, gap_note),
        )
        db.commit()
        created_blk = db.execute("SELECT * FROM challenge_blocks WHERE block_code=?", (b_code,)).fetchone()
    else:
        created_blk = None

    active_prof = _get_active_profile(db)
    blocks = [dict(r) for r in db.execute("SELECT * FROM challenge_blocks ORDER BY start_date ASC").fetchall()]
    if is_admin:
        enrollments = [
            dict(r)
            for r in db.execute(
                """SELECT e.*, p.client_name, p.start_weight_kg, p.target_weight_kg, p.target_calories, p.target_protein_g,
                          p.returning_member, a.email, a.username, a.invite_token,
                          CASE WHEN a.password_hash != '' THEN 1 ELSE 0 END AS has_password
                   FROM challenge_block_enrollments e
                   JOIN challenge_profiles p ON p.id = e.profile_id
                   LEFT JOIN challenge_user_accounts a ON a.profile_id = p.id
                   ORDER BY e.block_id, p.id"""
            ).fetchall()
        ]
        accts = [
            dict(r)
            for r in db.execute(
                """SELECT p.id AS profile_id, p.client_name, p.start_date, p.end_date, p.returning_member,
                          p.target_calories, p.target_protein_g, a.email, a.username, a.role, a.invite_token,
                          CASE WHEN a.password_hash != '' THEN 1 ELSE 0 END AS has_password
                   FROM challenge_profiles p
                   LEFT JOIN challenge_user_accounts a ON a.profile_id = p.id
                   ORDER BY p.id"""
            ).fetchall()
        ]
    else:
        enrollments = [
            dict(r)
            for r in db.execute(
                """SELECT e.*, p.client_name, p.start_weight_kg, p.target_weight_kg, p.target_calories, p.target_protein_g,
                          p.returning_member, a.email, a.username,
                          CASE WHEN a.password_hash != '' THEN 1 ELSE 0 END AS has_password
                   FROM challenge_block_enrollments e
                   JOIN challenge_profiles p ON p.id = e.profile_id
                   LEFT JOIN challenge_user_accounts a ON a.profile_id = p.id
                   WHERE e.profile_id=?
                   ORDER BY e.block_id, p.id""",
                (active_prof["id"],),
            ).fetchall()
        ]
        accts = [
            dict(r)
            for r in db.execute(
                """SELECT p.id AS profile_id, p.client_name, p.start_date, p.end_date, p.returning_member,
                          p.target_calories, p.target_protein_g, a.email, a.username, a.role,
                          CASE WHEN a.password_hash != '' THEN 1 ELSE 0 END AS has_password
                   FROM challenge_profiles p
                   LEFT JOIN challenge_user_accounts a ON a.profile_id = p.id
                   WHERE p.id=?""",
                (active_prof["id"],),
            ).fetchall()
        ]
    for b in blocks:
        b["members"] = [e for e in enrollments if e["block_id"] == b["id"]]
        b["member_count"] = len(b["members"])

    return jsonify({
        "ok": True,
        "active_profile_id": active_prof["id"],
        "active_client_name": active_prof["client_name"],
        "active_profile": active_prof,
        "block": dict(created_blk) if created_blk else None,
        "blocks": blocks,
        "users": accts,
    })


@challenge_blocks_bp.route("/api/challenge/blocks/join", methods=["POST"])
@challenge_blocks_bp.route("/api/challenge/blocks/webhook/enroll", methods=["POST"])
def api_challenge_block_join_or_webhook():
    """Invite acceptance or payment/signup form webhook to auto-enroll a user into an 8-week block."""
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    data = request.get_json() or {}
    code = (data.get("invite_code") or data.get("block_code") or "CS-OCT2026").strip().upper()
    cname = (data.get("client_name") or data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()

    # Prevent a public invite signup from hijacking an existing Admin account (Chris, Laura, Ewan) or password-protected account
    if not _is_current_user_admin(db):
        existing_acct = db.execute(
            """SELECT p.id, p.client_name, a.role, a.password_hash, a.email
               FROM challenge_profiles p
               LEFT JOIN challenge_user_accounts a ON a.profile_id = p.id
               WHERE LOWER(p.client_name)=LOWER(?) OR (? != '' AND LOWER(a.email)=LOWER(?))""",
            (cname, email, email),
        ).fetchone()
        if existing_acct:
            ex_role = (existing_acct["role"] or "").lower()
            ex_name = (existing_acct["client_name"] or "").strip().lower()
            if ex_role == "admin" or ex_name in ("ewan t", "chris", "laura") or existing_acct["password_hash"]:
                return jsonify({
                    "ok": False,
                    "error": "An account with this name or email already exists. Please use the Sign In tab instead.",
                }), 403

    block_row = db.execute(
        "SELECT * FROM challenge_blocks WHERE UPPER(invite_code)=? OR UPPER(block_code)=?",
        (code, code),
    ).fetchone()
    if not block_row:
        block_row = db.execute("SELECT * FROM challenge_blocks WHERE status='Active' ORDER BY start_date DESC LIMIT 1").fetchone()

    try:
        prof, acct = _upsert_challenger_for_block(db, data, dict(block_row))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    if data.get("auto_sign_in", True):
        session["challenge_profile_id"] = prof["id"]
        session["challenge_authed"] = True

    return jsonify({
        "ok": True,
        "block": dict(block_row),
        "profile_id": prof["id"],
        "client_name": prof["client_name"],
        "email": acct["email"],
        "invite_url": f"/challenge/login?invite={acct['invite_token']}&email={acct['email']}",
    })


@challenge_blocks_bp.route("/api/challenge/blocks/rollover", methods=["POST"])
def api_challenge_block_rollover():
    """Roll an existing challenger (or all members of a source block) over into the next 8-week block as Returning Members (14k min steps)."""
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    data = request.get_json() or {}
    from_block_id = int(data.get("from_block_id") or 0)
    target_block_id = int(data.get("to_block_id") or data.get("target_block_id") or 0)

    block_row = (
        db.execute("SELECT * FROM challenge_blocks WHERE id=?", (target_block_id,)).fetchone()
        if target_block_id
        else db.execute("SELECT * FROM challenge_blocks WHERE status='Upcoming' ORDER BY start_date ASC LIMIT 1").fetchone()
    )
    if not block_row:
        return jsonify({"ok": False, "error": "Target block not found"}), 404

    if from_block_id:
        if not _is_current_user_admin(db):
            return jsonify({"ok": False, "error": "Only Coach & Admin accounts can roll over an entire block."}), 403
        pids = [
            r["profile_id"]
            for r in db.execute(
                "SELECT profile_id FROM challenge_block_enrollments WHERE block_id=?",
                (from_block_id,),
            ).fetchall()
        ]
    else:
        active_prof = _get_active_profile(db)
        req_pid = int(data.get("profile_id") or active_prof["id"])
        if req_pid != int(active_prof["id"]) and not _is_current_user_admin(db):
            return jsonify({"ok": False, "error": "Only Coach & Admin accounts can roll over another challenger."}), 403
        pids = [req_pid]

    rolled = []
    for pid in pids:
        prof = db.execute("SELECT * FROM challenge_profiles WHERE id=?", (pid,)).fetchone()
        if not prof:
            continue
        latest_w_row = db.execute(
            "SELECT weight_kg FROM daily_checkins WHERE profile_id=? AND weight_kg IS NOT NULL ORDER BY date DESC LIMIT 1",
            (pid,),
        ).fetchone()
        new_start_w = float(data.get("start_weight_kg") or (latest_w_row["weight_kg"] if latest_w_row else prof["start_weight_kg"]))
        new_target_w = float(data.get("target_weight_kg") or round(new_start_w * 0.93, 1))
        updated_prof, _ = _upsert_challenger_for_block(
            db,
            {
                "client_name": prof["client_name"],
                "start_weight_kg": new_start_w,
                "target_weight_kg": new_target_w,
                "start_body_fat_pct": prof["start_body_fat_pct"],
                "target_body_fat_pct": prof["target_body_fat_pct"],
                "protein_g": prof["target_protein_g"],
                "returning_member": True,
                "workout_track": prof["workout_track"],
                "joined_via": f"Rollover → {block_row['block_code']}",
            },
            dict(block_row),
        )
        rolled.append(updated_prof)

    return jsonify({
        "ok": True,
        "block": dict(block_row),
        "rolled_over_count": len(rolled),
        "profile": rolled[0] if rolled else None,
        "message": f"Rolled {len(rolled)} challenger(s) into {block_row['name']} as Returning Members (14k steps)!",
    })


def _restore_backup_payload(db, payload, target_profile_id=None):
    import os
    pid = int(target_profile_id or payload.get("profile_id") or 1)
    counts = {"daily_checkins": 0, "daily_activities": 0, "workout_logs": 0, "weekly_submissions": 0, "progress_photos": 0}

    for c in payload.get("daily_checkins", []):
        d_str = (c.get("date") or "")[:10]
        if not d_str:
            continue
        db.execute(
            """INSERT INTO daily_checkins (
                profile_id, date, weight_kg, weigh_time, training_type, class_attended,
                steps, protein_g, calories, carbs_g, fats_g, fibre_g, water_l,
                sleep_mins, sleep_score, body_battery, resting_hr,
                morning_steps_banked, checkpoint_12pm_5k, checkpoint_5pm_10k,
                caffeine_cutoff_met, electrolytes_taken, stick_to_plan,
                mindset_win, notes, sync_source_garmin, sync_source_nutrition
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(profile_id, date) DO UPDATE SET
                weight_kg=COALESCE(excluded.weight_kg, daily_checkins.weight_kg),
                weigh_time=CASE WHEN excluded.weigh_time != '' THEN excluded.weigh_time ELSE daily_checkins.weigh_time END,
                training_type=excluded.training_type,
                steps=CASE WHEN excluded.steps > 0 THEN excluded.steps ELSE daily_checkins.steps END,
                protein_g=CASE WHEN excluded.protein_g > 0 THEN excluded.protein_g ELSE daily_checkins.protein_g END,
                calories=CASE WHEN excluded.calories > 0 THEN excluded.calories ELSE daily_checkins.calories END,
                carbs_g=CASE WHEN excluded.carbs_g > 0 THEN excluded.carbs_g ELSE daily_checkins.carbs_g END,
                fats_g=CASE WHEN excluded.fats_g > 0 THEN excluded.fats_g ELSE daily_checkins.fats_g END,
                fibre_g=CASE WHEN excluded.fibre_g > 0 THEN excluded.fibre_g ELSE daily_checkins.fibre_g END,
                water_l=CASE WHEN excluded.water_l > 0 THEN excluded.water_l ELSE daily_checkins.water_l END,
                sleep_mins=CASE WHEN excluded.sleep_mins > 0 THEN excluded.sleep_mins ELSE daily_checkins.sleep_mins END,
                sleep_score=COALESCE(excluded.sleep_score, daily_checkins.sleep_score),
                body_battery=COALESCE(excluded.body_battery, daily_checkins.body_battery),
                resting_hr=COALESCE(excluded.resting_hr, daily_checkins.resting_hr),
                stick_to_plan=excluded.stick_to_plan,
                mindset_win=CASE WHEN excluded.mindset_win != '' THEN excluded.mindset_win ELSE daily_checkins.mindset_win END,
                notes=CASE WHEN excluded.notes != '' THEN excluded.notes ELSE daily_checkins.notes END,
                sync_source_garmin=CASE WHEN excluded.sync_source_garmin != '' THEN excluded.sync_source_garmin ELSE daily_checkins.sync_source_garmin END,
                sync_source_nutrition=CASE WHEN excluded.sync_source_nutrition != '' THEN excluded.sync_source_nutrition ELSE daily_checkins.sync_source_nutrition END
            """,
            (
                pid, d_str, c.get("weight_kg"), c.get("weigh_time") or "", c.get("training_type") or "REST",
                c.get("class_attended") or "", int(c.get("steps") or 0), int(c.get("protein_g") or 0),
                int(c.get("calories") or 0), int(c.get("carbs_g") or 0), int(c.get("fats_g") or 0),
                int(c.get("fibre_g") or 0), float(c.get("water_l") or 0.0), int(c.get("sleep_mins") or 0),
                c.get("sleep_score"), c.get("body_battery"), c.get("resting_hr"),
                int(c.get("morning_steps_banked") or 0), int(c.get("checkpoint_12pm_5k") or 0),
                int(c.get("checkpoint_5pm_10k") or 0), int(c.get("caffeine_cutoff_met") or 0),
                int(c.get("electrolytes_taken") or 0), c.get("stick_to_plan") or "Y",
                c.get("mindset_win") or "", c.get("notes") or "",
                c.get("sync_source_garmin") or "", c.get("sync_source_nutrition") or "",
            ),
        )
        counts["daily_checkins"] += 1

    try:
        for a in payload.get("daily_activities", []):
            gid = str(a.get("garmin_activity_id") or "")
            if gid and db.execute("SELECT 1 FROM daily_activities WHERE profile_id=? AND garmin_activity_id=?", (pid, gid)).fetchone():
                continue
            db.execute(
                """INSERT INTO daily_activities (
                    profile_id, date, source, garmin_activity_id, activity_type, category,
                    title, start_time, duration_mins, distance_km, pace_str,
                    avg_hr, max_hr, calories, elevation_m, steps, notes
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    pid, (a.get("date") or "")[:10], a.get("source") or "Garmin Connect", gid,
                    a.get("activity_type") or "running", a.get("category") or "CARDIO",
                    a.get("title") or "Activity", a.get("start_time") or "",
                    a.get("duration_mins"), a.get("distance_km"), a.get("pace_str") or "",
                    a.get("avg_hr"), a.get("max_hr"), a.get("calories"),
                    a.get("elevation_m"), a.get("steps"), a.get("notes") or "",
                ),
            )
            counts["daily_activities"] += 1
    except Exception:
        pass

    for w in payload.get("workout_logs", []):
        db.execute(
            """INSERT INTO workout_logs (
                profile_id, track, workout_num, week_num, row_key,
                exercise_order, exercise_name, target_sets, target_reps,
                weight_reps, set_logs_json, logged_date, notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(profile_id, track, week_num, row_key) DO UPDATE SET
                weight_reps=excluded.weight_reps, set_logs_json=excluded.set_logs_json,
                logged_date=excluded.logged_date, notes=excluded.notes""",
            (
                pid, w.get("track") or "mens", int(w.get("workout_num") or 1), int(w.get("week_num") or 1),
                w.get("row_key") or "W1_A_1", w.get("exercise_order") or "A",
                w.get("exercise_name") or "Exercise", int(w.get("target_sets") or 1),
                str(w.get("target_reps") or "8"), w.get("weight_reps") or "",
                w.get("set_logs_json") or "[]", w.get("logged_date") or "2026-10-19", w.get("notes") or "",
            ),
        )
        counts["workout_logs"] += 1

    try:
        for s in payload.get("weekly_submissions", []):
            db.execute(
                """INSERT INTO weekly_submissions (profile_id, week_num, challenger_comments, coach_feedback, status, card_data_url)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(profile_id, week_num) DO UPDATE SET
                       challenger_comments=excluded.challenger_comments,
                       coach_feedback=CASE WHEN excluded.coach_feedback != '' THEN excluded.coach_feedback ELSE weekly_submissions.coach_feedback END,
                       status=excluded.status""",
                (
                    pid, int(s.get("week_num") or 0), s.get("challenger_comments") or "",
                    s.get("coach_feedback") or "", s.get("status") or "Submitted", s.get("card_data_url") or "",
                ),
            )
            counts["weekly_submissions"] += 1
    except Exception:
        pass

    for p in payload.get("progress_photos", []):
        if not p.get("photo_data_url"):
            continue
        exists = db.execute(
            "SELECT id FROM progress_photos WHERE profile_id=? AND week_num=? AND pose=?",
            (pid, int(p.get("week_num") or 1), p.get("pose") or "Front"),
        ).fetchone()
        if exists:
            db.execute(
                "UPDATE progress_photos SET photo_data_url=?, taken_date=?, weight_kg=? WHERE id=?",
                (p["photo_data_url"], p.get("taken_date") or "2026-10-19", p.get("weight_kg"), exists["id"]),
            )
        else:
            db.execute(
                """INSERT INTO progress_photos (profile_id, week_num, pose, taken_date, weight_kg, photo_data_url)
                   VALUES (?,?,?,?,?,?)""",
                (pid, int(p.get("week_num") or 1), p.get("pose") or "Front", p.get("taken_date") or "2026-10-19", p.get("weight_kg"), p["photo_data_url"]),
            )
        counts["progress_photos"] += 1

    db.commit()
    return counts


def _auto_seed_ewan_backup_if_empty(db):
    import os
    from flask import current_app
    try:
        if current_app.config.get("TESTING"):
            return
        cnt = db.execute("SELECT COUNT(*) AS c FROM daily_checkins WHERE profile_id=1 AND date >= '2026-10-19'").fetchone()["c"]
        if cnt >= 5:
            return
        seed_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "ewan_seed_backup.json"))
        if os.path.exists(seed_path):
            with open(seed_path, "r") as f:
                payload = json.load(f)
            _restore_backup_payload(db, payload, target_profile_id=1)
    except Exception:
        pass


@challenge_blocks_bp.route("/api/challenge/backup/export", methods=["GET"])
def api_challenge_backup_export():
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    prof = _get_active_profile(db)
    pid = prof["id"]
    payload = {
        "ok": True,
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "profile_id": pid,
        "client_name": prof["client_name"],
        "profile": prof,
        "daily_checkins": [dict(r) for r in db.execute("SELECT * FROM daily_checkins WHERE profile_id=? ORDER BY date", (pid,)).fetchall()],
        "workout_logs": [dict(r) for r in db.execute("SELECT * FROM workout_logs WHERE profile_id=? ORDER BY id", (pid,)).fetchall()],
        "progress_photos": [dict(r) for r in db.execute("SELECT * FROM progress_photos WHERE profile_id=? ORDER BY id", (pid,)).fetchall()],
    }
    for tbl in ("daily_activities", "weekly_submissions"):
        try:
            payload[tbl] = [dict(r) for r in db.execute(f"SELECT * FROM {tbl} WHERE profile_id=?", (pid,)).fetchall()]
        except Exception:
            payload[tbl] = []
    for k, val in list(payload.items()):
        if isinstance(val, list):
            for row in val:
                for col, v in list(row.items()):
                    if col in ("created_at", "updated_at", "submitted_at", "reviewed_at") and v is not None:
                        row[col] = str(v)
    return jsonify(payload)


@challenge_blocks_bp.route("/api/challenge/backup/import", methods=["POST"])
def api_challenge_backup_import():
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    data = request.get_json() or {}
    prof = _get_active_profile(db)
    pid = int(data.get("profile_id") or prof["id"])
    if pid != int(prof["id"]) and not _is_current_user_admin(db):
        pid = int(prof["id"])
    counts = _restore_backup_payload(db, data, target_profile_id=pid)
    return jsonify({"ok": True, "profile_id": pid, "restored": counts})


@challenge_blocks_bp.route("/challenge/admin")
def challenge_admin_page():
    """Dedicated Coach & Admin Portal for Chris, Laura, and Ewan."""
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    if not _is_current_user_admin(db):
        if session.get("challenge_authed"):
            return redirect("/challenge")
        return redirect(url_for("challenge_blocks.challenge_login_page"))
    return render_template("challenge_admin.html")


@challenge_blocks_bp.route("/api/challenge/admin/admins", methods=["GET"])
def api_challenge_list_admins():
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    if not _is_current_user_admin(db):
        return jsonify({"ok": False, "error": "Admin access required"}), 403
    rows = db.execute(
        """SELECT a.profile_id, a.username, a.email, a.role,
                  CASE WHEN a.password_hash != '' THEN 1 ELSE 0 END AS has_password,
                  p.client_name
           FROM challenge_user_accounts a
           JOIN challenge_profiles p ON p.id = a.profile_id
           WHERE a.role='admin' OR LOWER(p.client_name) IN ('ewan t', 'chris', 'laura')
           ORDER BY p.id"""
    ).fetchall()
    return jsonify({"ok": True, "admins": [dict(r) for r in rows]})


@challenge_blocks_bp.route("/api/challenge/admin/update-admin-account", methods=["POST"])
def api_challenge_update_admin_account():
    """Update email, username, role, or password for an admin or user account."""
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    is_admin = _is_current_user_admin(db)
    active_prof = _get_active_profile(db)
    data = request.get_json() or {}
    pid = int(data.get("profile_id") or active_prof["id"] or 0)
    if not is_admin:
        if pid != int(active_prof["id"]):
            return jsonify({"ok": False, "error": "Admin access required to update another account"}), 403
        role = "challenger"
    else:
        role = (data.get("role") or "admin").strip()
    email = (data.get("email") or "").strip().lower()
    new_pw = str(data.get("password") or "").strip()
    if not pid:
        return jsonify({"ok": False, "error": "profile_id is required"}), 400

    if email:
        db.execute(
            "UPDATE challenge_user_accounts SET email=?, role=?, updated_at=CURRENT_TIMESTAMP WHERE profile_id=?",
            (email, role, pid),
        )
    else:
        db.execute(
            "UPDATE challenge_user_accounts SET role=?, updated_at=CURRENT_TIMESTAMP WHERE profile_id=?",
            (role, pid),
        )
    if new_pw:
        pw_hash = bcrypt.hashpw(new_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        db.execute(
            "UPDATE challenge_user_accounts SET password_hash=?, updated_at=CURRENT_TIMESTAMP WHERE profile_id=?",
            (pw_hash, pid),
        )
    db.commit()
    acct = db.execute(
        """SELECT a.profile_id, a.username, a.email, a.role,
                  CASE WHEN a.password_hash != '' THEN 1 ELSE 0 END AS has_password,
                  p.client_name
           FROM challenge_user_accounts a
           JOIN challenge_profiles p ON p.id = a.profile_id
           WHERE a.profile_id=?""",
        (pid,),
    ).fetchone()
    return jsonify({"ok": True, "admin": dict(acct) if acct else None})


@challenge_blocks_bp.route("/api/challenge/admin/challenger-detail", methods=["GET"])
def api_challenge_admin_challenger_detail():
    """Return complete weekly data, 7-day sheet, week-over-week trajectory, check-in submissions & all photos for a challenger."""
    from challenge import _build_week_sheet
    from challenge_progress import compute_week_over_week

    db = get_db()
    ensure_blocks_and_auth_tables(db)
    if not _is_current_user_admin(db):
        return jsonify({"ok": False, "error": "Admin access required (Chris, Laura, or Ewan only)"}), 403
    pid = int(request.args.get("profile_id") or 1)
    week_num = int(request.args.get("week") if request.args.get("week") is not None else 1)

    p_row = db.execute("SELECT * FROM challenge_profiles WHERE id=?", (pid,)).fetchone()
    if not p_row:
        p_row = db.execute("SELECT * FROM challenge_profiles ORDER BY id LIMIT 1").fetchone()
    profile = dict(p_row)
    profile["weekly_targets"] = json.loads(profile.get("weekly_targets_json", "[]") or "[]")

    acct = db.execute("SELECT username, email, role, invite_token FROM challenge_user_accounts WHERE profile_id=?", (profile["id"],)).fetchone()
    profile["email"] = acct["email"] if acct else ""
    profile["role"] = acct["role"] if acct else "challenger"
    profile["invite_token"] = acct["invite_token"] if acct else ""

    week_sheet = _build_week_sheet(db, profile, week_num)
    for row in week_sheet.get("rows", []):
        for k in ("created_at", "updated_at"):
            if row.get(k) is not None:
                row[k] = str(row[k])
        try:
            acts = [
                dict(a)
                for a in db.execute(
                    "SELECT id, source, title, category, duration_mins, distance_km, calories FROM daily_activities WHERE profile_id=? AND date=?",
                    (profile["id"], row["date"]),
                ).fetchall()
            ]
        except Exception:
            acts = []
        row["activities"] = acts
    week_sheet["days"] = week_sheet.get("rows", [])
    week_sheet["week_start"] = week_sheet.get("start_date", "")
    week_sheet["week_end"] = week_sheet.get("end_date", "")
    week_sheet["target_steps"] = week_sheet.get("step_target", 10000)

    for k in ("created_at", "updated_at"):
        if profile.get(k) is not None:
            profile[k] = str(profile[k])

    wow = compute_week_over_week(db, profile)

    photos = [
        dict(r)
        for r in db.execute(
            """SELECT id, profile_id, week_num, pose, taken_date, weight_kg, notes, photo_data_url
               FROM progress_photos WHERE profile_id=? ORDER BY week_num ASC, id ASC""",
            (profile["id"],),
        ).fetchall()
    ]

    subs = [
        dict(r)
        for r in db.execute(
            """SELECT * FROM weekly_submissions WHERE profile_id=? ORDER BY week_num DESC""",
            (profile["id"],),
        ).fetchall()
    ]
    for s in subs:
        for k in ("submitted_at", "reviewed_at", "updated_at"):
            if s.get(k) is not None:
                s[k] = str(s[k])

    return jsonify({
        "ok": True,
        "profile": profile,
        "selected_week": week_num,
        "week_sheet": week_sheet,
        "week_over_week": wow,
        "photos": photos,
        "submissions": subs,
    })


@challenge_blocks_bp.route("/api/challenge/admin/cohort-summary", methods=["GET"])
def api_challenge_admin_cohort_summary():
    """High-speed summary table for ~100+ challengers across a cohort block & week, with click-through to full details."""
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    if not _is_current_user_admin(db):
        return jsonify({"ok": False, "error": "Admin access required (Chris, Laura, or Ewan only)"}), 403
    week_num = int(request.args.get("week") if request.args.get("week") is not None else 1)
    block_id_filter = int(request.args.get("block_id") or 0)

    profiles = [
        dict(r)
        for r in db.execute(
            """SELECT p.*, COALESCE(a.email, '') AS email, COALESCE(a.role, 'challenger') AS role,
                      e.block_id, COALESCE(b.name, 'Block 1 · Oct–Dec 2026') AS block_name,
                      COALESCE(b.invite_code, 'CS-OCT2026') AS invite_code
               FROM challenge_profiles p
               LEFT JOIN challenge_user_accounts a ON a.profile_id = p.id
               LEFT JOIN challenge_block_enrollments e ON e.profile_id = p.id
               LEFT JOIN challenge_blocks b ON b.id = e.block_id
               WHERE LOWER(p.client_name) NOT IN ('chris', 'laura')
               ORDER BY p.id ASC"""
        ).fetchall()
    ]

    # Deduplicate in case a challenger is enrolled in multiple blocks (pick matching block_id_filter or latest)
    by_pid = {}
    for p in profiles:
        if block_id_filter and p.get("block_id") != block_id_filter:
            continue
        by_pid[p["id"]] = p

    subs_map = {
        r["profile_id"]: dict(r)
        for r in db.execute("SELECT * FROM weekly_submissions WHERE week_num=?", (week_num,)).fetchall()
    }
    photos_map = {
        r["profile_id"]: r["cnt"]
        for r in db.execute(
            "SELECT profile_id, COUNT(*) AS cnt FROM progress_photos WHERE week_num=? AND photo_data_url != '' GROUP BY profile_id",
            (week_num,),
        ).fetchall()
    }

    roster = []
    for pid, p in by_pid.items():
        start_dt = datetime.strptime((p.get("start_date") or "2026-10-19")[:10], "%Y-%m-%d")
        wk_start = (start_dt - timedelta(days=7)) if week_num == 0 else (start_dt + timedelta(days=(week_num - 1) * 7))
        wk_end = wk_start + timedelta(days=6)
        d_start_str, d_end_str = wk_start.strftime("%Y-%m-%d"), wk_end.strftime("%Y-%m-%d")

        base_step = 14000 if p.get("returning_member") else 10000
        step_target = base_step if week_num == 0 else max(base_step, 10000 + (min(8, week_num) - 1) * 1000)
        wk_target_w = round(float(p.get("start_weight_kg") or 84.0) * (0.99 ** max(0, week_num - 1)), 2)

        agg = db.execute(
            """SELECT COUNT(*) AS days_logged,
                      SUM(CASE WHEN stick_to_plan='Y' THEN 1 ELSE 0 END) AS days_on_plan,
                      AVG(CASE WHEN weight_kg > 0 THEN weight_kg END) AS avg_w,
                      AVG(CASE WHEN steps > 0 THEN steps END) AS avg_s,
                      AVG(CASE WHEN calories > 0 THEN calories END) AS avg_c,
                      AVG(CASE WHEN protein_g > 0 THEN protein_g END) AS avg_p,
                      AVG(CASE WHEN water_l > 0 THEN water_l END) AS avg_wat
               FROM daily_checkins
               WHERE profile_id=? AND date >= ? AND date <= ?
                 AND (steps > 0 OR calories > 0 OR weight_kg IS NOT NULL OR water_l > 0)""",
            (pid, d_start_str, d_end_str),
        ).fetchone()

        avg_w = round(float(agg["avg_w"]), 2) if agg and agg["avg_w"] else None
        start_w = float(p.get("start_weight_kg") or 84.0)
        delta_w = round(avg_w - start_w, 2) if avg_w is not None else None
        sub = subs_map.get(pid, {})
        status = sub.get("status") or ("In Progress" if (agg and agg["days_logged"] > 0) else "No Logs Yet")

        roster.append({
            "profile_id": pid,
            "client_name": p["client_name"],
            "email": p["email"],
            "role": p["role"],
            "goal": p.get("goal") or "Weight Loss",
            "returning_member": bool(p.get("returning_member")),
            "block_id": p.get("block_id") or 1,
            "block_name": p.get("block_name") or "Block 1 · Oct–Dec 2026",
            "invite_code": p.get("invite_code") or "CS-OCT2026",
            "start_weight_kg": start_w,
            "target_weight_kg": float(p.get("target_weight_kg") or 78.3),
            "week_target_weight_kg": wk_target_w,
            "target_calories": int(p.get("target_calories") or 2173),
            "target_protein_g": int(p.get("target_protein_g") or 150),
            "target_water_l": float(p.get("target_water_l") or 3.66),
            "step_target": step_target,
            "days_logged": int(agg["days_logged"] or 0) if agg else 0,
            "days_on_plan": int(agg["days_on_plan"] or 0) if agg else 0,
            "avg_weight_kg": avg_w,
            "weight_delta_kg": delta_w,
            "avg_steps": int(round(float(agg["avg_s"] or 0))) if agg else 0,
            "avg_calories": int(round(float(agg["avg_c"] or 0))) if agg else 0,
            "avg_protein_g": int(round(float(agg["avg_p"] or 0))) if agg else 0,
            "avg_water_l": round(float(agg["avg_wat"] or 0.0), 2) if agg else 0.0,
            "photos_count": int(photos_map.get(pid, 0)),
            "photos_required": (week_num != 1),
            "checkin_day": "Monday (Day 1 Start)" if week_num == 0 else "Friday",
            "checkin_date": start_dt.strftime("%Y-%m-%d") if week_num == 0 else (wk_start + timedelta(days=4)).strftime("%Y-%m-%d"),
            "submission_status": status,
            "challenger_comments": sub.get("challenger_comments") or "",
            "coach_feedback": sub.get("coach_feedback") or "",
        })

    kpis = {
        "total_challengers": len(roster),
        "needs_review": sum(1 for r in roster if r["submission_status"] == "Submitted"),
        "reviewed": sum(1 for r in roster if r["submission_status"] == "Reviewed"),
        "low_logging": sum(1 for r in roster if r["days_logged"] < 3),
        "with_photos": sum(1 for r in roster if r["photos_count"] > 0),
    }
    return jsonify({"ok": True, "week": week_num, "kpis": kpis, "roster": roster})



