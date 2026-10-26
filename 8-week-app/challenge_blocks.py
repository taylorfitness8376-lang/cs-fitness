from flask import Blueprint, jsonify, render_template, request, redirect, session, url_for
from datetime import datetime, timedelta
import bcrypt
import json
import re
import secrets

from database import get_db, calculate_challenge_targets, init_challenge_tables
from challenge import _get_active_profile

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

    # Ensure every profile has a row in challenge_user_accounts
    for p in db.execute("SELECT id, client_name FROM challenge_profiles").fetchall():
        existing = db.execute("SELECT profile_id FROM challenge_user_accounts WHERE profile_id=?", (p["id"],)).fetchone()
        if not existing:
            slug = re.sub(r"[^a-z0-9]", "", p["client_name"].split()[0].lower()) or f"user{p['id']}"
            clash = db.execute("SELECT 1 FROM challenge_user_accounts WHERE username=?", (slug,)).fetchone()
            uname = f"{slug}{p['id']}" if clash else slug
            default_email = "taylor.ewan@gmail.com" if p["client_name"] == "Ewan t" else f"{uname}@taylorfitness.co.uk"
            role = "admin" if p["client_name"] == "Ewan t" else "challenger"
            db.execute(
                """INSERT OR IGNORE INTO challenge_user_accounts (profile_id, username, email, role, invite_token)
                   VALUES (?,?,?,?,?)""",
                (p["id"], uname, default_email, role, secrets.token_urlsafe(12)),
            )
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
    role = data.get("role") if data.get("role") in ("challenger", "coach", "admin") else "challenger"

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
    active_prof = _get_active_profile(db)
    return render_template(
        "challenge_login.html",
        blocks=blocks,
        active_profile=active_prof,
        invite_code=request.args.get("code", ""),
        invite_token=request.args.get("invite", ""),
        email_prefill=request.args.get("email", ""),
    )


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
    pid = int(data.get("profile_id") or _get_active_profile(db)["id"])
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

    acct = db.execute("SELECT * FROM challenge_user_accounts WHERE profile_id=?", (pid,)).fetchone()
    if acct and acct["password_hash"] and session.get("challenge_profile_id") != pid:
        if not raw_pw or not bcrypt.checkpw(raw_pw.encode("utf-8"), acct["password_hash"].encode("utf-8")):
            return jsonify({"ok": False, "requires_password": True, "error": "Password required for this challenger profile."}), 401

    session["challenge_profile_id"] = pid
    session["challenge_authed"] = True
    prof = _get_active_profile(db, pid)
    return jsonify({"ok": True, "profile": prof, "client_name": prof["client_name"]})


@challenge_blocks_bp.route("/api/challenge/blocks", methods=["GET", "POST"])
def api_challenge_blocks():
    db = get_db()
    ensure_blocks_and_auth_tables(db)

    if request.method == "POST":
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

    blocks = [dict(r) for r in db.execute("SELECT * FROM challenge_blocks ORDER BY start_date ASC").fetchall()]
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
    for b in blocks:
        b["members"] = [e for e in enrollments if e["block_id"] == b["id"]]
        b["member_count"] = len(b["members"])

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
    active_prof = _get_active_profile(db)
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
        pids = [
            r["profile_id"]
            for r in db.execute(
                "SELECT profile_id FROM challenge_block_enrollments WHERE block_id=?",
                (from_block_id,),
            ).fetchall()
        ]
    else:
        pids = [int(data.get("profile_id") or _get_active_profile(db)["id"])]

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
