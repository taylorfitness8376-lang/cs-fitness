from flask import Blueprint, jsonify, render_template, request, redirect, session, url_for
from datetime import datetime, timedelta
import bcrypt
import json
import re
import secrets

from database import get_db, calculate_challenge_targets, init_challenge_tables
from challenge import (
    _get_active_profile,
    _is_current_user_admin,
    _set_authenticated_session,
    _check_challenge_api_auth,
    _get_profile_integrations,
)

challenge_blocks_bp = Blueprint("challenge_blocks", __name__)


@challenge_blocks_bp.before_request
def _guard_challenge_blocks_bp_routes():
    return _check_challenge_api_auth()


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


_ENSURED_BLOCK_DBS = set()
_DEFAULT_CSFITNESS_PW_HASH = bcrypt.hashpw(b"csfitness", bcrypt.gensalt()).decode("utf-8")


def ensure_blocks_and_auth_tables(db):
    db_key = None
    try:
        for r in db.execute("PRAGMA database_list").fetchall():
            if r["name"] == "main":
                db_key = r["file"] or None
                break
    except Exception:
        db_key = None
    if db_key and db_key in _ENSURED_BLOCK_DBS:
        try:
            has_acct = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='challenge_user_accounts'"
            ).fetchone()
            has_ewan = (
                db.execute("SELECT 1 FROM challenge_user_accounts WHERE profile_id=1 AND role='challenger'").fetchone()
                if has_acct
                else None
            )
            has_ewan_admin = (
                db.execute("SELECT 1 FROM challenge_user_accounts WHERE LOWER(email)='taylor.ewan@googlemail.com' AND role='admin'").fetchone()
                if has_acct
                else None
            )
            if has_acct and has_ewan and has_ewan_admin:
                return
        except Exception:
            pass
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
        "ALTER TABLE challenge_user_accounts ADD COLUMN reset_code TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE challenge_user_accounts ADD COLUMN reset_expires_at TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE challenge_user_accounts ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE challenge_user_accounts ADD COLUMN verification_token TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE challenge_user_accounts ADD COLUMN verified_at TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE challenge_user_accounts ADD COLUMN teamup_customer_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE challenge_user_accounts ADD COLUMN teamup_status TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE challenge_profiles ADD COLUMN first_name TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE challenge_profiles ADD COLUMN last_name TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE challenge_profiles ADD COLUMN age INTEGER",
        "ALTER TABLE challenge_profiles ADD COLUMN initial_checkin_notes TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE challenge_profiles ADD COLUMN onboarding_completed INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE challenge_block_enrollments ADD COLUMN block_start_weight_kg REAL",
        "ALTER TABLE challenge_block_enrollments ADD COLUMN initial_checkin_notes TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE challenge_block_enrollments ADD COLUMN onboarding_completed INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE challenge_block_enrollments ADD COLUMN welcome_email_sent INTEGER NOT NULL DEFAULT 0",
    ):
        try:
            db.execute(col_sql)
        except Exception:
            pass

    db.execute(
        """CREATE TABLE IF NOT EXISTS teamup_integration_settings (
            id                      INTEGER PRIMARY KEY CHECK (id = 1),
            enabled                 INTEGER NOT NULL DEFAULT 0,
            provider_id             TEXT NOT NULL DEFAULT '',
            api_key_set             INTEGER NOT NULL DEFAULT 0,
            api_key_b64             TEXT NOT NULL DEFAULT '',
            webhook_secret          TEXT NOT NULL DEFAULT '',
            auto_enroll_block_code  TEXT NOT NULL DEFAULT 'CS-OCT2026',
            sync_class_attendance   INTEGER NOT NULL DEFAULT 1,
            last_webhook_at         TEXT NOT NULL DEFAULT '',
            updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    t_row = db.execute("SELECT id, webhook_secret FROM teamup_integration_settings WHERE id=1").fetchone()
    if not t_row:
        db.execute(
            "INSERT INTO teamup_integration_settings (id, webhook_secret, auto_enroll_block_code, sync_class_attendance) VALUES (1, ?, 'CS-OCT2026', 1)",
            (f"tu_{secrets.token_urlsafe(14)}",),
        )

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

    # Migrate profile_id=1 from legacy "Ewan t" to "Ewan Taylor" and keep it as Ewan's personal Challenger account
    try:
        db.execute(
            """UPDATE challenge_profiles
               SET client_name='Ewan Taylor',
                   first_name='Ewan',
                   last_name='Taylor'
               WHERE id=1 AND (LOWER(client_name) IN ('ewan t', 'ewan') OR LOWER(COALESCE(last_name, '')) IN ('', 't'))"""
        )
        p1_row = db.execute("SELECT id FROM challenge_profiles WHERE id=1").fetchone()
        if p1_row:
            db.execute(
                """INSERT INTO challenge_user_accounts (profile_id, username, email, role, invite_token, email_verified, verification_token)
                   VALUES (1, 'ewan', 'taylor.ewan@gmail.com', 'challenger', ?, 1, ?)
                   ON CONFLICT(profile_id) DO UPDATE SET
                       role='challenger',
                       email=CASE WHEN challenge_user_accounts.email='' OR LOWER(challenge_user_accounts.email)='taylor.ewan@googlemail.com' THEN 'taylor.ewan@gmail.com' ELSE challenge_user_accounts.email END""",
                (secrets.token_urlsafe(12), secrets.token_urlsafe(18)),
            )
    except Exception:
        pass

    # Ensure the 3 separate Admin accounts (Ewan Admin: taylor.ewan@googlemail.com / csfitness, Chris, Laura) exist
    admin_seeds = [
        ("Ewan (Admin)", "ewan_admin", "taylor.ewan@googlemail.com", "mens", _DEFAULT_CSFITNESS_PW_HASH),
        ("Chris", "chris", "chris@cs.fitness", "mens", ""),
        ("Laura", "laura", "laura@cs.fitness", "ladies", ""),
    ]
    for cname, uname, default_email, track, default_pw_hash in admin_seeds:
        p_row = db.execute("SELECT id FROM challenge_profiles WHERE LOWER(client_name)=LOWER(?)", (cname,)).fetchone()
        if not p_row:
            calc = calculate_challenge_targets(80.0, 75.0, 16.0, 14.0, 150, "2026-10-19", "Coach / Admin", False)
            db.execute(
                """INSERT INTO challenge_profiles (
                    client_name, first_name, last_name, goal, start_date, end_date,
                    start_weight_kg, target_weight_kg, start_body_fat_pct, target_body_fat_pct,
                    lean_body_mass_kg, fat_mass_kg, to_lose_kg,
                    target_calories, target_protein_g, target_fats_g, target_carbs_g,
                    target_fibre_g, target_water_l, target_sleep_hrs,
                    returning_member, workout_track, weekly_targets_json, onboarding_completed
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    cname, cname.split()[0], "Taylor" if "ewan" in cname.lower() else "", "Coach / Admin", "2026-10-19", calc["end_date"],
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
                """INSERT INTO challenge_user_accounts (profile_id, username, email, password_hash, role, invite_token, email_verified, verification_token)
                   VALUES (?,?,?,?,?,?,1,?)
                   ON CONFLICT(profile_id) DO UPDATE SET role='admin',
                       email_verified=1,
                       email=CASE WHEN challenge_user_accounts.email='' THEN excluded.email ELSE challenge_user_accounts.email END,
                       password_hash=CASE WHEN challenge_user_accounts.password_hash='' AND excluded.password_hash!='' THEN excluded.password_hash ELSE challenge_user_accounts.password_hash END""",
                (p_row["id"], uname, default_email, default_pw_hash, "admin", secrets.token_urlsafe(12), secrets.token_urlsafe(18)),
            )
            db.execute("DELETE FROM challenge_block_enrollments WHERE profile_id=?", (p_row["id"],))

    # Ensure core enrolled challengers (including Alan Mackay) exist permanently across container restarts
    challenger_seeds = [
        ("Alan Mackay", "alan", "", "mens", 86.0, 80.0, 18.0, 15.0, 150),
    ]
    for cname, uname, default_email, track, sw, tw, sbf, tbf, prot_g in challenger_seeds:
        p_row = db.execute("SELECT id FROM challenge_profiles WHERE LOWER(client_name)=LOWER(?)", (cname,)).fetchone()
        if not p_row:
            calc = calculate_challenge_targets(sw, tw, sbf, tbf, prot_g, "2026-10-19", "Weight Loss", False)
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
                    cname, "Weight Loss", "2026-10-19", calc["end_date"],
                    sw, tw, sbf, tbf,
                    calc["lean_body_mass_kg"], calc["fat_mass_kg"], calc["to_lose_kg"],
                    calc["target_calories"], calc["target_protein_g"], calc["target_fats_g"], calc["target_carbs_g"],
                    calc["target_fibre_g"], calc["target_water_l"], calc["target_sleep_hrs"],
                    0, track, json.dumps(calc["weekly_targets"]),
                ),
            )
            p_row = db.execute("SELECT id FROM challenge_profiles WHERE LOWER(client_name)=LOWER(?)", (cname,)).fetchone()
        if p_row:
            db.execute(
                """INSERT INTO challenge_user_accounts (profile_id, username, email, role, invite_token, email_verified, verification_token)
                   VALUES (?,?,?,?,?,0,?)
                   ON CONFLICT(profile_id) DO UPDATE SET
                       email=CASE WHEN challenge_user_accounts.email='' THEN excluded.email ELSE challenge_user_accounts.email END,
                       invite_token=CASE WHEN challenge_user_accounts.invite_token='' THEN excluded.invite_token ELSE challenge_user_accounts.invite_token END""",
                (p_row["id"], uname, default_email, "challenger", secrets.token_urlsafe(12), secrets.token_urlsafe(18)),
            )

    # Ensure every profile has a row in challenge_user_accounts and is enrolled in the active block
    active_blk = db.execute("SELECT id FROM challenge_blocks WHERE block_code='2026-B5-OCT' OR status='Active' ORDER BY id LIMIT 1").fetchone()
    for p in db.execute("SELECT id, client_name, returning_member FROM challenge_profiles").fetchall():
        existing = db.execute("SELECT profile_id, verification_token, invite_token FROM challenge_user_accounts WHERE profile_id=?", (p["id"],)).fetchone()
        if not existing:
            slug = re.sub(r"[^a-z0-9]", "", p["client_name"].split()[0].lower()) or f"user{p['id']}"
            clash = db.execute("SELECT 1 FROM challenge_user_accounts WHERE username=?", (slug,)).fetchone()
            uname = f"{slug}{p['id']}" if clash else slug
            default_email = "taylor.ewan@gmail.com" if p["client_name"].lower() in ("ewan taylor", "ewan t") else f"{uname}@taylorfitness.co.uk"
            is_adm = p["client_name"].lower() in ("ewan (admin)", "ewan admin", "chris", "laura")
            role = "admin" if is_adm else "challenger"
            db.execute(
                """INSERT OR IGNORE INTO challenge_user_accounts (
                    profile_id, username, email, role, invite_token, email_verified, verification_token
                ) VALUES (?,?,?,?,?,?,?)""",
                (p["id"], uname, default_email, role, secrets.token_urlsafe(12), 1 if is_adm else 0, secrets.token_urlsafe(18)),
            )
        else:
            if not existing["verification_token"]:
                db.execute(
                    "UPDATE challenge_user_accounts SET verification_token=? WHERE profile_id=?",
                    (secrets.token_urlsafe(18), p["id"]),
                )
            if not existing["invite_token"]:
                db.execute(
                    "UPDATE challenge_user_accounts SET invite_token=? WHERE profile_id=?",
                    (secrets.token_urlsafe(12), p["id"]),
                )
        if active_blk and p["client_name"].lower() not in ("chris", "laura", "ewan (admin)", "ewan admin"):
            db.execute(
                """INSERT OR IGNORE INTO challenge_block_enrollments (block_id, profile_id, is_returning, joined_via)
                   VALUES (?,?,?,?)""",
                (active_blk["id"], p["id"], int(p["returning_member"] or 0), "Cohort Seed"),
            )
    _auto_seed_ewan_backup_if_empty(db)
    # Backfill first_name, last_name, and onboarding_completed for existing users with photos/check-ins
    try:
        for prow in db.execute("SELECT id, client_name, first_name, last_name, onboarding_completed FROM challenge_profiles").fetchall():
            parts = (prow["client_name"] or "").strip().split(None, 1)
            fn = prow["first_name"] or (parts[0] if parts else "")
            ln = prow["last_name"] or (parts[1] if len(parts) > 1 else ("Taylor" if prow["id"] == 1 else ""))
            has_w0_photos = db.execute(
                "SELECT COUNT(*) AS c FROM progress_photos WHERE profile_id=? AND week_num=0 AND photo_data_url != ''",
                (prow["id"],),
            ).fetchone()["c"] >= 1
            onb = 1 if (prow["onboarding_completed"] or has_w0_photos or prow["id"] == 1) else 0
            db.execute(
                "UPDATE challenge_profiles SET first_name=?, last_name=?, onboarding_completed=? WHERE id=?",
                (fn, ln, onb, prow["id"]),
            )
    except Exception:
        pass
    db.commit()
    if db_key:
        _ENSURED_BLOCK_DBS.add(db_key)


def _send_challenge_email(to_email, subject, text_body, html_body=None):
    """Send a transactional email via SMTP or Resend HTTP API when configured."""
    import os
    import smtplib
    from email.message import EmailMessage

    to_email = (to_email or "").strip()
    if not to_email or "@" not in to_email:
        return {"sent": False, "method": "none"}

    # 1. Resend HTTP API (ideal for Render/cloud hosts)
    resend_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    if resend_key:
        try:
            import urllib.request
            payload = {
                "from": os.environ.get("SMTP_FROM") or "CS Fitness 8-Week Challenge <onboarding@resend.dev>",
                "to": [to_email],
                "subject": subject,
                "text": text_body,
            }
            if html_body:
                payload["html"] = html_body
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=7)
            return {"sent": True, "method": "resend"}
        except Exception:
            pass

    # 2. Standard SMTP (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS)
    smtp_host = (os.environ.get("SMTP_HOST") or "").strip()
    if smtp_host:
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or "noreply@cs.fitness"
            msg["To"] = to_email
            msg.set_content(text_body)
            if html_body:
                msg.add_alternative(html_body, subtype="html")
            smtp_port = int(os.environ.get("SMTP_PORT") or 587)
            with smtplib.SMTP(smtp_host, smtp_port, timeout=8) as server:
                server.starttls()
                if os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"):
                    server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
                server.send_message(msg)
            return {"sent": True, "method": "smtp"}
        except Exception:
            pass

    return {"sent": False, "method": "verification_link_ready"}


def _send_verification_email(db, profile_id, base_url=None):
    """Ensure a verification token exists and send a clickable verification email to the user."""
    acct = db.execute(
        """SELECT a.*, p.client_name FROM challenge_user_accounts a
           JOIN challenge_profiles p ON p.id = a.profile_id
           WHERE a.profile_id=?""",
        (profile_id,),
    ).fetchone()
    if not acct:
        return {"sent": False, "verification_url": "", "verification_token": ""}

    token = (acct["verification_token"] or "").strip() if "verification_token" in acct.keys() else ""
    if not token:
        token = secrets.token_urlsafe(20)
        db.execute(
            "UPDATE challenge_user_accounts SET verification_token=?, updated_at=CURRENT_TIMESTAMP WHERE profile_id=?",
            (token, profile_id),
        )
        db.commit()

    host_prefix = (base_url or "").rstrip("/")
    rel_url = f"/challenge/verify-email?token={token}"
    full_url = f"{host_prefix}{rel_url}" if host_prefix else rel_url

    subject = "Verify your email — CS Fitness 8-Week Challenge"
    text_body = (
        f"Hi {acct['client_name']} (@{acct['username']}),\n\n"
        f"Welcome to the CS Fitness 8-Week Challenge!\n"
        f"Please click the link below to verify your email address ({acct['email']}):\n\n"
        f"{full_url}\n\n"
        f"Sign-In Email: {acct['email']}\n"
        f"Username: {acct['username']}\n"
    )
    html_body = (
        f"<div style='font-family:sans-serif;max-width:520px;padding:24px;background:#0a0f0c;color:#f8fafc;border-radius:12px;border:1px solid #3DFF4F'>"
        f"<h2 style='color:#3DFF4F;margin-top:0'>CS FITNESS · 8-WEEK CHALLENGE</h2>"
        f"<p>Hi <strong>{acct['client_name']}</strong> (<code>@{acct['username']}</code>),</p>"
        f"<p>Your challenger account has been created. Click the button below to verify your email address (<strong>{acct['email']}</strong>):</p>"
        f"<p style='margin:24px 0'><a href='{full_url}' style='background:#3DFF4F;color:#050806;padding:12px 22px;border-radius:8px;font-weight:800;text-decoration:none;display:inline-block'>✅ Verify Email Address</a></p>"
        f"<p style='font-size:12px;color:#94a3b8'>Or copy &amp; paste this link: {full_url}</p>"
        f"</div>"
    )
    mail_res = _send_challenge_email(acct["email"], subject, text_body, html_body)
    return {
        "sent": mail_res["sent"],
        "method": mail_res["method"],
        "verification_url": rel_url,
        "full_verification_url": full_url,
        "verification_token": token,
    }


def _send_block_welcome_email(db, profile_id, block_row, is_returning_user=False, base_url=None):
    """Send cohort block welcome email (New Password flow for new users, direct Block Access flow for returning users)."""
    acct = db.execute(
        """SELECT a.*, p.client_name, p.first_name FROM challenge_user_accounts a
           JOIN challenge_profiles p ON p.id = a.profile_id
           WHERE a.profile_id=?""",
        (profile_id,),
    ).fetchone()
    if not acct:
        return {"sent": False, "welcome_url": "", "full_welcome_url": ""}

    host_prefix = (base_url or "").rstrip("/")
    b_name = block_row.get("name") or "CS Fitness 8-Week Challenge"
    inv_code = block_row.get("invite_code") or "CS-OCT2026"
    invite_tok = acct["invite_token"] or secrets.token_urlsafe(12)
    greet_name = (acct["first_name"] or acct["client_name"] or "Challenger").split()[0]

    if is_returning_user:
        rel_url = f"/challenge/login?email={acct['email']}&code={inv_code}&returning=1"
        full_url = f"{host_prefix}{rel_url}" if host_prefix else rel_url
        subject = f"Welcome Back to {b_name} — Your Cohort Access is Ready!"
        text_body = (
            f"Hi {greet_name},\n\n"
            f"Your payment has been processed and your access to {b_name} ({block_row.get('start_date', '')}) is now unlocked!\n"
            f"Since you have already been in a previous block, sign in with your existing password:\n\n"
            f"{full_url}\n\n"
            f"On your 1st login for this block, you'll be prompted to enter your new block starting weight, upload your 3 starting photos (Side, Front, Back), and add your initial check-in notes for Coach Chris.\n"
        )
        html_body = (
            f"<div style='font-family:sans-serif;max-width:540px;padding:24px;background:#0a0f0c;color:#f8fafc;border-radius:12px;border:1px solid #3DFF4F'>"
            f"<h2 style='color:#3DFF4F;margin-top:0'>WELCOME BACK · {b_name}</h2>"
            f"<p>Hi <strong>{greet_name}</strong>,</p>"
            f"<p>You have been added to <strong>{b_name}</strong> (starting <strong>{block_row.get('start_date', '')}</strong>). Since you already have a CS Fitness account from a previous cohort, sign in using your existing password:</p>"
            f"<p style='margin:24px 0'><a href='{full_url}' style='background:#3DFF4F;color:#050806;padding:12px 22px;border-radius:8px;font-weight:800;text-decoration:none;display:inline-block'>🚀 Sign In &amp; Complete Day 1 Block Setup →</a></p>"
            f"<p style='font-size:13px;color:#cbd5e1'>On 1st login for this block, enter your starting weight, upload your 3 starting photos (Side, Front, Back), and capture your initial check-in notes.</p>"
            f"</div>"
        )
    else:
        rel_url = f"/challenge/login?invite={invite_tok}&email={acct['email']}&code={inv_code}"
        full_url = f"{host_prefix}{rel_url}" if host_prefix else rel_url
        subject = f"Welcome to {b_name} — Set Your Password & Complete Day 1 Setup"
        text_body = (
            f"Hi {greet_name},\n\n"
            f"Welcome to the CS Fitness 8-Week Challenge ({b_name}, starting {block_row.get('start_date', '')})!\n"
            f"Click your personal sign-up link below to create your password, confirm your profile details (First Name, Last Name, Age, Starting Weight), upload your 3 starting photos, and add your initial check-in notes:\n\n"
            f"{full_url}\n\n"
            f"Cohort Block Code: {inv_code}\n"
        )
        html_body = (
            f"<div style='font-family:sans-serif;max-width:540px;padding:24px;background:#0a0f0c;color:#f8fafc;border-radius:12px;border:1px solid #3DFF4F'>"
            f"<h2 style='color:#3DFF4F;margin-top:0'>WELCOME TO {b_name.upper()}</h2>"
            f"<p>Hi <strong>{greet_name}</strong>,</p>"
            f"<p>You are enrolled in <strong>{b_name}</strong> (starting <strong>{block_row.get('start_date', '')}</strong>). Click your personal onboarding link below to create your password and complete your Day 1 Setup (starting weight, 3 starting photos &amp; initial check-in notes):</p>"
            f"<p style='margin:24px 0'><a href='{full_url}' style='background:#3DFF4F;color:#050806;padding:12px 22px;border-radius:8px;font-weight:800;text-decoration:none;display:inline-block'>✅ Set Password &amp; Start Cohort Setup →</a></p>"
            f"<p style='font-size:12px;color:#94a3b8'>Cohort Code: <strong>{inv_code}</strong> · Direct Link: {full_url}</p>"
            f"</div>"
        )

    mail_res = _send_challenge_email(acct["email"], subject, text_body, html_body)
    return {
        "sent": mail_res["sent"],
        "method": mail_res["method"],
        "is_returning_user": bool(is_returning_user),
        "welcome_url": rel_url,
        "full_welcome_url": full_url,
    }


def _upsert_challenger_for_block(db, data, block_row):
    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    cname = (data.get("client_name") or data.get("name") or "").strip()
    if not cname and (first_name or last_name):
        cname = f"{first_name} {last_name}".strip()
    email = (data.get("email") or "").strip().lower()
    req_username = re.sub(r"[^a-z0-9_.-]", "", (data.get("username") or "").strip().lower())
    teamup_cid = str(data.get("teamup_customer_id") or "").strip()
    req_invite_token = str(data.get("invite_token") or "").strip()
    age_val = int(data["age"]) if str(data.get("age") or "").strip().isdigit() else None
    init_notes = (data.get("initial_checkin_notes") or "").strip()

    # Check if an account already exists by invite_token, email, username, teamup_customer_id, or client_name so we reuse its profile
    existing_by_acct = None
    if req_invite_token:
        existing_by_acct = db.execute(
            """SELECT p.id, p.client_name FROM challenge_user_accounts a
               JOIN challenge_profiles p ON p.id = a.profile_id
               WHERE a.invite_token=? AND a.invite_token != ''""",
            (req_invite_token,),
        ).fetchone()
    if not existing_by_acct and email:
        existing_by_acct = db.execute(
            """SELECT p.id, p.client_name FROM challenge_user_accounts a
               JOIN challenge_profiles p ON p.id = a.profile_id
               WHERE LOWER(a.email)=?""",
            (email,),
        ).fetchone()
    if not existing_by_acct and req_username:
        existing_by_acct = db.execute(
            """SELECT p.id, p.client_name FROM challenge_user_accounts a
               JOIN challenge_profiles p ON p.id = a.profile_id
               WHERE LOWER(a.username)=?""",
            (req_username,),
        ).fetchone()
    if not existing_by_acct and teamup_cid:
        existing_by_acct = db.execute(
            """SELECT p.id, p.client_name FROM challenge_user_accounts a
               JOIN challenge_profiles p ON p.id = a.profile_id
               WHERE a.teamup_customer_id=? AND a.teamup_customer_id != ''""",
            (teamup_cid,),
        ).fetchone()
    if not existing_by_acct and cname:
        existing_by_acct = db.execute(
            "SELECT id, client_name FROM challenge_profiles WHERE LOWER(client_name)=LOWER(?)",
            (cname,),
        ).fetchone()

    if existing_by_acct and not cname:
        cname = existing_by_acct["client_name"]
    elif existing_by_acct and cname.lower() != existing_by_acct["client_name"].lower():
        cname = existing_by_acct["client_name"]
    elif existing_by_acct:
        cname = existing_by_acct["client_name"]

    if not cname and req_username:
        cname = req_username.replace("_", " ").replace(".", " ").title()
    if not cname and email:
        cname = email.split("@")[0].replace(".", " ").title()
    if not cname:
        raise ValueError("Name or email is required")

    if not first_name and cname:
        parts = cname.split(None, 1)
        first_name = parts[0] if parts else ""
        if not last_name and len(parts) > 1:
            last_name = parts[1]

    # Check if user was already in a previous block or already has a password set
    prior_enroll_cnt = 0
    existing_has_pw = False
    if existing_by_acct:
        prior_enroll_cnt = db.execute(
            "SELECT COUNT(*) AS c FROM challenge_block_enrollments WHERE profile_id=? AND block_id!=?",
            (existing_by_acct["id"], block_row["id"]),
        ).fetchone()["c"]
        pw_row = db.execute(
            "SELECT password_hash FROM challenge_user_accounts WHERE profile_id=?",
            (existing_by_acct["id"],),
        ).fetchone()
        existing_has_pw = bool(pw_row and pw_row["password_hash"])

    returning = bool(data.get("returning_member", False)) or (prior_enroll_cnt > 0)
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
            client_name, first_name, last_name, age, initial_checkin_notes, onboarding_completed,
            goal, start_date, end_date,
            start_weight_kg, target_weight_kg, start_body_fat_pct, target_body_fat_pct,
            lean_body_mass_kg, fat_mass_kg, to_lose_kg,
            target_calories, target_protein_g, target_fats_g, target_carbs_g,
            target_fibre_g, target_water_l, target_sleep_hrs,
            returning_member, workout_track, weekly_targets_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(client_name) DO UPDATE SET
            first_name=CASE WHEN excluded.first_name != '' THEN excluded.first_name ELSE challenge_profiles.first_name END,
            last_name=CASE WHEN excluded.last_name != '' THEN excluded.last_name ELSE challenge_profiles.last_name END,
            age=COALESCE(excluded.age, challenge_profiles.age),
            initial_checkin_notes=CASE WHEN excluded.initial_checkin_notes != '' THEN excluded.initial_checkin_notes ELSE challenge_profiles.initial_checkin_notes END,
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
            first_name,
            last_name,
            age_val,
            init_notes,
            1 if data.get("onboarding_completed") else 0,
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
        """INSERT INTO challenge_block_enrollments (
               block_id, profile_id, is_returning, joined_via, payment_ref,
               block_start_weight_kg, initial_checkin_notes, onboarding_completed
           )
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(block_id, profile_id) DO UPDATE SET
               is_returning=excluded.is_returning,
               joined_via=excluded.joined_via,
               block_start_weight_kg=COALESCE(excluded.block_start_weight_kg, challenge_block_enrollments.block_start_weight_kg),
               initial_checkin_notes=CASE WHEN excluded.initial_checkin_notes != '' THEN excluded.initial_checkin_notes ELSE challenge_block_enrollments.initial_checkin_notes END,
               payment_ref=CASE WHEN excluded.payment_ref != '' THEN excluded.payment_ref ELSE challenge_block_enrollments.payment_ref END""",
        (
            block_row["id"],
            pid,
            1 if returning else 0,
            data.get("joined_via", "Invite / Signup"),
            str(data.get("payment_ref") or ""),
            start_w,
            init_notes,
            1 if data.get("onboarding_completed") else 0,
        ),
    )

    base_slug = req_username or re.sub(r"[^a-z0-9]", "", cname.split()[0].lower()) or f"user{pid}"
    clash = db.execute("SELECT 1 FROM challenge_user_accounts WHERE LOWER(username)=LOWER(?) AND profile_id!=?", (base_slug, pid)).fetchone()
    uname = f"{base_slug}{pid}" if clash else base_slug
    raw_pw = str(data.get("password") or "").strip()
    pw_hash = bcrypt.hashpw(raw_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8") if raw_pw else ""
    invite_token = secrets.token_urlsafe(12)
    verif_token = secrets.token_urlsafe(20)
    teamup_cid = str(data.get("teamup_customer_id") or "").strip()
    teamup_st = str(data.get("teamup_status") or ("Linked" if teamup_cid else "")).strip()
    is_admin_caller = _is_current_user_admin(db)
    if cname.strip().lower() in ("ewan (admin)", "ewan admin", "chris", "laura") or email == "taylor.ewan@googlemail.com":
        role = "admin"
    elif is_admin_caller and data.get("role") in ("challenger", "coach", "admin"):
        role = data.get("role")
    else:
        role = "challenger"

    db.execute(
        """INSERT INTO challenge_user_accounts (
               profile_id, username, email, password_hash, role, invite_token,
               email_verified, verification_token, teamup_customer_id, teamup_status
           )
           VALUES (?,?,?,?,?,?,0,?,?,?)
           ON CONFLICT(profile_id) DO UPDATE SET
               username=CASE WHEN ? != '' THEN excluded.username ELSE challenge_user_accounts.username END,
               email=CASE WHEN excluded.email != '' THEN excluded.email ELSE challenge_user_accounts.email END,
               password_hash=CASE WHEN excluded.password_hash != '' THEN excluded.password_hash ELSE challenge_user_accounts.password_hash END,
               verification_token=CASE WHEN challenge_user_accounts.verification_token = '' THEN excluded.verification_token ELSE challenge_user_accounts.verification_token END,
               teamup_customer_id=CASE WHEN excluded.teamup_customer_id != '' THEN excluded.teamup_customer_id ELSE challenge_user_accounts.teamup_customer_id END,
               teamup_status=CASE WHEN excluded.teamup_status != '' THEN excluded.teamup_status ELSE challenge_user_accounts.teamup_status END,
               role=excluded.role,
               updated_at=CURRENT_TIMESTAMP""",
        (
            pid,
            uname,
            email or f"{uname}@taylorfitness.co.uk",
            pw_hash,
            role,
            invite_token,
            verif_token,
            teamup_cid,
            teamup_st,
            req_username,
        ),
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
    active_acct = None
    if active_prof:
        r = db.execute("SELECT * FROM challenge_user_accounts WHERE profile_id=?", (active_prof["id"],)).fetchone()
        active_acct = dict(r) if r else None

    invite_token = (request.args.get("invite") or "").strip()
    user_hint = (request.args.get("user") or "").strip().lower()
    invited_user = None
    if invite_token or user_hint:
        q_row = None
        if invite_token:
            q_row = db.execute(
                """SELECT p.*, a.username, a.email, a.invite_token, a.role,
                          CASE WHEN a.password_hash != '' THEN 1 ELSE 0 END AS has_password
                   FROM challenge_user_accounts a
                   JOIN challenge_profiles p ON p.id = a.profile_id
                   WHERE a.invite_token=?""",
                (invite_token,),
            ).fetchone()
        if not q_row and user_hint:
            q_row = db.execute(
                """SELECT p.*, a.username, a.email, a.invite_token, a.role,
                          CASE WHEN a.password_hash != '' THEN 1 ELSE 0 END AS has_password
                   FROM challenge_user_accounts a
                   JOIN challenge_profiles p ON p.id = a.profile_id
                   WHERE LOWER(a.username)=? OR LOWER(p.client_name)=?""",
                (user_hint, user_hint),
            ).fetchone()
        if q_row:
            invited_user = dict(q_row)

    email_prefill = request.args.get("email", "")
    if not email_prefill and invited_user and invited_user.get("email"):
        email_prefill = invited_user["email"]

    return render_template(
        "challenge_login.html",
        blocks=blocks,
        active_profile=active_prof,
        active_account=active_acct,
        is_authenticated=is_authed,
        invite_code=request.args.get("code", ""),
        invite_token=invite_token or (invited_user["invite_token"] if invited_user else ""),
        invited_user=invited_user,
        email_prefill=email_prefill,
        verified_banner=request.args.get("verified", "") == "1",
    )


@challenge_blocks_bp.route("/challenge/verify-email", methods=["GET"])
@challenge_blocks_bp.route("/api/challenge/auth/verify-email", methods=["GET", "POST"])
def api_challenge_verify_email():
    """Verify a challenger's email address when they click the verification link sent on account creation."""
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    token = (
        request.args.get("token")
        or ((request.get_json(silent=True) or {}).get("token") if request.method == "POST" else "")
        or ""
    ).strip()

    wants_json = (
        request.path.startswith("/api/")
        or request.method == "POST"
        or "application/json" in (request.headers.get("Accept") or "")
    )
    if not token:
        if wants_json:
            return jsonify({"ok": False, "error": "Missing verification token."}), 400
        return redirect(url_for("challenge_blocks.challenge_login_page"))

    acct = db.execute(
        """SELECT a.*, p.client_name FROM challenge_user_accounts a
           JOIN challenge_profiles p ON p.id = a.profile_id
           WHERE a.verification_token=?""",
        (token,),
    ).fetchone()
    if not acct:
        if wants_json:
            return jsonify({"ok": False, "error": "Invalid or expired email verification token."}), 404
        return redirect(url_for("challenge_blocks.challenge_login_page"))

    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        """UPDATE challenge_user_accounts
           SET email_verified=1, verified_at=?, updated_at=CURRENT_TIMESTAMP
           WHERE profile_id=?""",
        (now_str, acct["profile_id"]),
    )
    db.commit()

    prof = _get_active_profile(db, acct["profile_id"]) or dict(db.execute("SELECT * FROM challenge_profiles WHERE id=?", (acct["profile_id"],)).fetchone())
    _set_authenticated_session(prof, dict(acct))

    if wants_json:
        return jsonify({
            "ok": True,
            "profile_id": acct["profile_id"],
            "client_name": acct["client_name"],
            "username": acct["username"],
            "email": acct["email"],
            "email_verified": True,
            "verified_at": now_str,
            "message": f"Email {acct['email']} verified! Welcome, {acct['client_name']} (@{acct['username']}).",
        })
    return redirect(url_for("challenge_blocks.challenge_login_page", verified="1", email=acct["email"]))


@challenge_blocks_bp.route("/api/challenge/auth/resend-verification", methods=["POST"])
def api_challenge_resend_verification():
    """Resend the email verification link to the user's email address."""
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    data = request.get_json(silent=True) or {}
    ident = (data.get("email") or data.get("username") or "").strip().lower()
    pid = data.get("profile_id")

    if pid:
        acct = db.execute("SELECT * FROM challenge_user_accounts WHERE profile_id=?", (int(pid),)).fetchone()
    elif ident:
        acct = db.execute(
            "SELECT * FROM challenge_user_accounts WHERE LOWER(email)=? OR LOWER(username)=?",
            (ident, ident),
        ).fetchone()
    else:
        active_prof = _get_active_profile(db)
        acct = db.execute("SELECT * FROM challenge_user_accounts WHERE profile_id=?", (active_prof["id"],)).fetchone() if active_prof else None

    if not acct:
        return jsonify({"ok": False, "error": "Account not found."}), 404

    v_res = _send_verification_email(db, acct["profile_id"], request.host_url.rstrip("/"))
    return jsonify({
        "ok": True,
        "profile_id": acct["profile_id"],
        "email": acct["email"],
        "username": acct["username"],
        "email_sent": v_res["sent"],
        "verification_url": v_res["verification_url"],
        "full_verification_url": v_res["full_verification_url"],
        "message": (
            f"Verification email sent to {acct['email']}!"
            if v_res["sent"]
            else f"Verification link generated for {acct['email']} — click to verify."
        ),
    })


@challenge_blocks_bp.route("/api/challenge/auth/logout", methods=["POST", "GET"])
def api_challenge_auth_logout():
    for k in (
        "challenge_profile_id",
        "challenge_authed",
        "challenge_client_name",
        "challenge_email",
        "challenge_username",
        "challenge_role",
        "challenge_start_weight_kg",
        "challenge_target_weight_kg",
        "challenge_workout_track",
    ):
        session.pop(k, None)
    if request.method == "GET":
        return redirect(url_for("challenge_blocks.challenge_login_page"))
    return jsonify({"ok": True})


@challenge_blocks_bp.route("/api/challenge/auth/status", methods=["GET"])
def api_challenge_auth_status():
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    is_authed = bool(session.get("challenge_authed"))
    prof = _get_active_profile(db)
    if not prof:
        enr = db.execute("SELECT * FROM challenge_blocks WHERE status='Active' LIMIT 1").fetchone()
        return jsonify({
            "ok": True,
            "authenticated": False,
            "profile_id": None,
            "client_name": "",
            "username": "",
            "email": "",
            "email_verified": False,
            "teamup_customer_id": "",
            "role": "guest",
            "has_password": False,
            "active_block": dict(enr) if enr else None,
        })
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
        "authenticated": is_authed,
        "profile_id": prof["id"],
        "client_name": prof["client_name"],
        "username": acct["username"] if acct else "",
        "email": acct["email"] if acct else "",
        "email_verified": bool(acct and acct["email_verified"]) if acct and "email_verified" in acct.keys() else False,
        "teamup_customer_id": acct["teamup_customer_id"] if acct and "teamup_customer_id" in acct.keys() else "",
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

    if not ident:
        return jsonify({"ok": False, "error": "Please enter your email address."}), 400

    acct = db.execute(
        """SELECT a.*, p.client_name FROM challenge_user_accounts a
           JOIN challenge_profiles p ON p.id = a.profile_id
           WHERE LOWER(a.email)=? OR LOWER(a.username)=? OR LOWER(p.client_name)=?""",
        (ident, ident, ident),
    ).fetchone()
    if not acct:
        return jsonify({"ok": False, "error": "No account found for that email address. Use the Create Account / Join Block tab to sign up."}), 404

    if acct["password_hash"]:
        if not raw_pw or not bcrypt.checkpw(raw_pw.encode("utf-8"), acct["password_hash"].encode("utf-8")):
            return jsonify({"ok": False, "error": "Incorrect password. Click 'Forgot password?' below if you need to reset it."}), 401
    elif raw_pw:
        # First-time password setup on login if account had no password yet
        pw_hash = bcrypt.hashpw(raw_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        db.execute("UPDATE challenge_user_accounts SET password_hash=?, updated_at=CURRENT_TIMESTAMP WHERE profile_id=?", (pw_hash, acct["profile_id"]))
        db.commit()

    prof = dict(db.execute("SELECT * FROM challenge_profiles WHERE id=?", (acct["profile_id"],)).fetchone())
    _set_authenticated_session(prof, dict(acct))
    return jsonify({
        "ok": True,
        "profile_id": acct["profile_id"],
        "client_name": acct["client_name"],
        "username": acct["username"],
        "email": acct["email"],
        "email_verified": bool(acct["email_verified"]) if "email_verified" in acct.keys() else False,
        "role": acct["role"],
    })


@challenge_blocks_bp.route("/api/challenge/auth/update-account", methods=["POST"])
def api_challenge_update_account():
    """Update a user's email address, username (handle), or display name."""
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    data = request.get_json() or {}
    active_prof = _get_active_profile(db)
    pid = int(data.get("profile_id") or active_prof["id"])
    if pid != int(active_prof["id"]) and not _is_current_user_admin(db):
        return jsonify({"ok": False, "error": "Cannot modify another user's account."}), 403

    new_email = (data.get("email") or "").strip().lower()
    new_username = re.sub(r"[^a-z0-9_.-]", "", (data.get("username") or "").strip().lower())
    new_name = (data.get("client_name") or "").strip()
    teamup_cid = (data.get("teamup_customer_id") or "").strip()

    acct = db.execute("SELECT * FROM challenge_user_accounts WHERE profile_id=?", (pid,)).fetchone()
    if not acct:
        return jsonify({"ok": False, "error": "Account not found."}), 404

    if new_username and new_username != (acct["username"] or "").lower():
        clash = db.execute(
            "SELECT 1 FROM challenge_user_accounts WHERE LOWER(username)=? AND profile_id!=?",
            (new_username, pid),
        ).fetchone()
        if clash:
            return jsonify({"ok": False, "error": f"Username '@{new_username}' is already taken."}), 409

    if new_email and new_email != (acct["email"] or "").lower():
        clash = db.execute(
            "SELECT 1 FROM challenge_user_accounts WHERE LOWER(email)=? AND profile_id!=?",
            (new_email, pid),
        ).fetchone()
        if clash:
            return jsonify({"ok": False, "error": f"Email '{new_email}' is already linked to another account."}), 409

    email_changed = bool(new_email and new_email != (acct["email"] or "").lower())
    db.execute(
        """UPDATE challenge_user_accounts
           SET email=CASE WHEN ? != '' THEN ? ELSE email END,
               username=CASE WHEN ? != '' THEN ? ELSE username END,
               teamup_customer_id=CASE WHEN ? != '' THEN ? ELSE teamup_customer_id END,
               email_verified=CASE WHEN ? = 1 THEN 0 ELSE email_verified END,
               verification_token=CASE WHEN ? = 1 THEN ? ELSE verification_token END,
               updated_at=CURRENT_TIMESTAMP
           WHERE profile_id=?""",
        (
            new_email, new_email,
            new_username, new_username,
            teamup_cid, teamup_cid,
            1 if email_changed else 0,
            1 if email_changed else 0,
            secrets.token_urlsafe(20),
            pid,
        ),
    )
    if new_name:
        db.execute("UPDATE challenge_profiles SET client_name=? WHERE id=?", (new_name, pid))
    db.commit()

    v_res = None
    if email_changed:
        v_res = _send_verification_email(db, pid, request.host_url.rstrip("/"))

    updated = db.execute(
        """SELECT a.*, p.client_name FROM challenge_user_accounts a
           JOIN challenge_profiles p ON p.id = a.profile_id WHERE a.profile_id=?""",
        (pid,),
    ).fetchone()
    if session.get("challenge_profile_id") and int(session.get("challenge_profile_id")) == int(pid):
        prof_row = db.execute("SELECT * FROM challenge_profiles WHERE id=?", (pid,)).fetchone()
        if prof_row:
            _set_authenticated_session(dict(prof_row), dict(updated))
    return jsonify({
        "ok": True,
        "profile_id": pid,
        "client_name": updated["client_name"],
        "username": updated["username"],
        "email": updated["email"],
        "email_verified": bool(updated["email_verified"]),
        "verification_url": v_res["verification_url"] if v_res else "",
        "message": "Account details updated!",
    })


@challenge_blocks_bp.route("/api/challenge/auth/set-password", methods=["POST"])
def api_challenge_set_password():
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    new_pw = str(data.get("new_password") or data.get("password") or "").strip()
    curr_pw = str(data.get("current_password") or "").strip()

    active_prof = _get_active_profile(db)
    if active_prof:
        pid = int(data.get("profile_id") or active_prof["id"])
        if pid != int(active_prof["id"]) and not _is_current_user_admin(db):
            return jsonify({"ok": False, "error": "Cannot modify another user's password."}), 403
        acct = db.execute("SELECT * FROM challenge_user_accounts WHERE profile_id=?", (pid,)).fetchone()
    elif email:
        acct = db.execute("SELECT * FROM challenge_user_accounts WHERE LOWER(email)=?", (email,)).fetchone()
        if not acct:
            return jsonify({"ok": False, "error": "Account not found."}), 404
        pid = int(acct["profile_id"])
    else:
        return jsonify({"ok": False, "error": "Authentication required."}), 401

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


@challenge_blocks_bp.route("/api/challenge/auth/forgot-password", methods=["POST"])
def api_challenge_forgot_password():
    """Generate a 6-digit password reset code (and send via Email/Telegram when configured)."""
    import os
    import smtplib
    from email.message import EmailMessage

    db = get_db()
    ensure_blocks_and_auth_tables(db)
    data = request.get_json() or {}
    ident = (data.get("email") or data.get("username") or "").strip().lower()
    if not ident:
        return jsonify({"ok": False, "error": "Please enter your email address or full name."}), 400

    acct = db.execute(
        """SELECT a.*, p.client_name FROM challenge_user_accounts a
           JOIN challenge_profiles p ON p.id = a.profile_id
           WHERE LOWER(a.email)=? OR LOWER(a.username)=? OR LOWER(p.client_name)=?""",
        (ident, ident, ident),
    ).fetchone()
    if not acct:
        return jsonify({
            "ok": False,
            "error": "No account found with that email or name. Please check your spelling or join using your Block Invite Code.",
        }), 404

    reset_code = f"{secrets.randbelow(900000) + 100000}"
    expires_at = (datetime.utcnow() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        """UPDATE challenge_user_accounts
           SET reset_code=?, reset_expires_at=?, updated_at=CURRENT_TIMESTAMP
           WHERE profile_id=?""",
        (reset_code, expires_at, acct["profile_id"]),
    )
    db.commit()

    delivery = []
    reset_url = f"{request.host_url.rstrip('/')}/challenge/login?reset=1&email={acct['email']}&code={reset_code}"
    mail_res = _send_challenge_email(
        acct["email"],
        f"CS Fitness 8-Week Challenge — Password Reset ({reset_code})",
        (
            f"Hi {acct['client_name']} (@{acct['username']}),\n\n"
            f"Your CS Fitness 8-Week Challenge password reset code is: {reset_code}\n"
            f"(Valid for 30 minutes.)\n\n"
            f"Or click this link to reset your password directly:\n{reset_url}\n"
        ),
        (
            f"<div style='font-family:sans-serif;max-width:520px;padding:24px;background:#0a0f0c;color:#f8fafc;border-radius:12px;border:1px solid #3DFF4F'>"
            f"<h2 style='color:#3DFF4F;margin-top:0'>Password Reset Request</h2>"
            f"<p>Hi <strong>{acct['client_name']}</strong> (<code>@{acct['username']}</code>),</p>"
            f"<p>Your 6-digit password reset code is: <strong style='font-size:20px;color:#3DFF4F'>{reset_code}</strong></p>"
            f"<p style='margin:22px 0'><a href='{reset_url}' style='background:#3DFF4F;color:#050806;padding:12px 22px;border-radius:8px;font-weight:800;text-decoration:none;display:inline-block'>🔑 Reset Password Now</a></p>"
            f"</div>"
        ),
    )
    if mail_res.get("sent"):
        delivery.append("email")

    try:
        intg = _get_profile_integrations(db, acct["profile_id"], include_secrets=True)
        tg_token = (intg.get("telegram_bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
        tg_chat = (intg.get("telegram_chat_id") or "").strip()
        if tg_token and tg_chat:
            import urllib.request
            payload_bytes = json.dumps({
                "chat_id": tg_chat,
                "text": f"🔐 *CS Fitness Password Reset*\nHi {acct['client_name']}, your 6-digit password reset code is: `{reset_code}` (valid 30 mins).",
                "parse_mode": "Markdown",
            }).encode("utf-8")
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{tg_token}/sendMessage",
                data=payload_bytes,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
            delivery.append("telegram")
    except Exception:
        pass

    if delivery:
        msg_str = f"6-digit reset code sent via {', '.join(delivery)}! Enter it below (or enter your Block Invite Code, e.g. CS-OCT2026) to set a new password."
    else:
        msg_str = "Reset request created! Enter your Cohort Block Invite Code (e.g. CS-OCT2026) or the 6-digit code from your Coach below to set your new password immediately."

    return jsonify({
        "ok": True,
        "email": acct["email"],
        "client_name": acct["client_name"],
        "delivery": delivery,
        "message": msg_str,
    })


@challenge_blocks_bp.route("/api/challenge/auth/reset-password", methods=["POST"])
def api_challenge_reset_password():
    """Reset a forgotten password using a 6-digit reset code, personal invite token, or Cohort Block Invite Code."""
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    data = request.get_json() or {}
    ident = (data.get("email") or data.get("username") or "").strip().lower()
    verification = (
        data.get("verification_code")
        or data.get("verification")
        or data.get("reset_code")
        or data.get("invite_code")
        or data.get("code")
        or ""
    ).strip()
    new_pw = str(data.get("new_password") or data.get("password") or "").strip()

    if not ident:
        return jsonify({"ok": False, "error": "Please enter your email address or full name."}), 400
    if len(new_pw) < 4:
        return jsonify({"ok": False, "error": "New password must be at least 4 characters."}), 400
    if not verification:
        return jsonify({
            "ok": False,
            "error": "Please enter your Block Invite Code (e.g. CS-OCT2026) or 6-digit Reset Code to verify.",
        }), 400

    acct = db.execute(
        """SELECT a.*, p.client_name FROM challenge_user_accounts a
           JOIN challenge_profiles p ON p.id = a.profile_id
           WHERE LOWER(a.email)=? OR LOWER(a.username)=? OR LOWER(p.client_name)=?""",
        (ident, ident, ident),
    ).fetchone()
    if not acct:
        return jsonify({"ok": False, "error": "Account not found. Check your email or full name."}), 404

    verified = False
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    saved_code = (acct["reset_code"] or "").strip() if "reset_code" in acct.keys() else ""
    saved_exp = (acct["reset_expires_at"] or "").strip() if "reset_expires_at" in acct.keys() else ""

    # 1. Check 6-digit reset_code
    if saved_code and verification == saved_code and (not saved_exp or saved_exp >= now_str):
        verified = True

    # 2. Check personal invite_token
    if not verified and acct["invite_token"] and verification == acct["invite_token"]:
        verified = True

    # 3. Check Cohort Block Invite Code (e.g. CS-OCT2026)
    if not verified:
        matching_block = db.execute(
            """SELECT b.id FROM challenge_blocks b
               LEFT JOIN challenge_block_enrollments e ON e.block_id = b.id AND e.profile_id = ?
               WHERE (UPPER(b.invite_code)=UPPER(?) OR UPPER(b.block_code)=UPPER(?))
                 AND (e.profile_id IS NOT NULL OR b.status='Active')""",
            (acct["profile_id"], verification, verification),
        ).fetchone()
        if matching_block:
            # Protect admin accounts unless caller is admin or matched their personal token/reset code or exact email
            is_admin_acct = (acct["role"] or "").lower() == "admin"
            if not is_admin_acct or ident == (acct["email"] or "").lower():
                verified = True

    if not verified:
        return jsonify({
            "ok": False,
            "error": "Invalid verification code. Enter your Block Invite Code (e.g. CS-OCT2026) or a valid 6-digit Reset Code.",
        }), 401

    pw_hash = bcrypt.hashpw(new_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    db.execute(
        """UPDATE challenge_user_accounts
           SET password_hash=?, reset_code='', reset_expires_at='', updated_at=CURRENT_TIMESTAMP
           WHERE profile_id=?""",
        (pw_hash, acct["profile_id"]),
    )
    db.commit()

    if data.get("auto_sign_in", True):
        prof_row = db.execute("SELECT * FROM challenge_profiles WHERE id=?", (acct["profile_id"],)).fetchone()
        if prof_row:
            _set_authenticated_session(dict(prof_row), dict(acct))

    return jsonify({
        "ok": True,
        "profile_id": acct["profile_id"],
        "client_name": acct["client_name"],
        "email": acct["email"],
        "role": acct["role"],
        "message": f"Password reset! Signed in as {acct['client_name']}.",
    })


@challenge_blocks_bp.route("/api/challenge/admin/reset-user-password", methods=["POST"])
def api_admin_reset_user_password():
    """Allow Coaches & Admins (Chris, Laura, Ewan) to set or clear any challenger's password in 1 click."""
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    if not _is_current_user_admin(db):
        return jsonify({"ok": False, "error": "Only Coach & Admin accounts can reset user passwords."}), 403

    data = request.get_json() or {}
    pid = int(data.get("profile_id") or 0)
    new_pw = str(data.get("new_password") or "").strip()
    acct = db.execute(
        """SELECT a.*, p.client_name FROM challenge_user_accounts a
           JOIN challenge_profiles p ON p.id = a.profile_id
           WHERE a.profile_id=?""",
        (pid,),
    ).fetchone()
    if not acct:
        return jsonify({"ok": False, "error": "Challenger account not found."}), 404

    if new_pw:
        if len(new_pw) < 4:
            return jsonify({"ok": False, "error": "Temporary password must be at least 4 characters."}), 400
        pw_hash = bcrypt.hashpw(new_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        msg = f"Password for {acct['client_name']} set to the new temporary password."
    else:
        pw_hash = ""
        msg = f"Password cleared for {acct['client_name']} — their next login will save whatever password they type."

    db.execute(
        """UPDATE challenge_user_accounts
           SET password_hash=?, reset_code='', reset_expires_at='', updated_at=CURRENT_TIMESTAMP
           WHERE profile_id=?""",
        (pw_hash, pid),
    )
    db.commit()
    return jsonify({"ok": True, "profile_id": pid, "client_name": acct["client_name"], "message": msg})


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

    prof = dict(db.execute("SELECT * FROM challenge_profiles WHERE id=?", (pid,)).fetchone())
    _set_authenticated_session(prof, dict(acct) if acct else None)
    return jsonify({"ok": True, "profile": _get_active_profile(db, pid), "client_name": prof["client_name"]})


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
        start_date = (data.get("start_date") or data.get("week1_monday") or "2027-01-11")[:10]
        if not name:
            return jsonify({"ok": False, "error": "Block name is required"}), 400
        dt_start = datetime.strptime(start_date, "%Y-%m-%d")
        pre_dt = (data.get("pre_coaching_date") or data.get("pre_coaching_Start") or (dt_start - timedelta(days=7)).strftime("%Y-%m-%d"))[:10]
        end_dt = (dt_start + timedelta(days=56)).strftime("%Y-%m-%d")
        b_code = (data.get("block_code") or f"{dt_start.strftime('%Y')}-B-{dt_start.strftime('%b').upper()}").strip().upper()
        inv_code = (data.get("invite_code") or f"CS-{dt_start.strftime('%b%Y').upper()}").strip().upper()
        status = data.get("status") if data.get("status") in ("Active", "Upcoming", "Completed") else "Upcoming"
        gap_note = (data.get("gap_note") or "8-week cohort block + 1-week pre-coaching").strip()

        if status == "Active":
            db.execute("UPDATE challenge_blocks SET status='Completed' WHERE status='Active' AND start_date < ?", (start_date,))

        existing_blk = db.execute(
            "SELECT * FROM challenge_blocks WHERE block_code=? OR invite_code=?",
            (b_code, inv_code),
        ).fetchone()
        if existing_blk:
            db.execute(
                """UPDATE challenge_blocks
                   SET name=?, pre_coaching_date=?, start_date=?, end_date=?, status=?, gap_note=?
                   WHERE id=?""",
                (name, pre_dt, start_date, end_dt, status, gap_note, existing_blk["id"]),
            )
            db.commit()
            created_blk = db.execute("SELECT * FROM challenge_blocks WHERE id=?", (existing_blk["id"],)).fetchone()
        else:
            db.execute(
                """INSERT INTO challenge_blocks (block_code, name, pre_coaching_date, start_date, end_date, status, invite_code, gap_note)
                   VALUES (?,?,?,?,?,?,?,?)""",
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
                          p.returning_member, a.email, a.username, a.invite_token, a.email_verified,
                          a.teamup_customer_id, a.teamup_status,
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
                """SELECT p.*, p.id AS profile_id, a.email, a.username, a.role, a.invite_token,
                          a.email_verified, a.teamup_customer_id, a.teamup_status,
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
                          p.returning_member, a.email, a.username, a.email_verified,
                          a.teamup_customer_id, a.teamup_status,
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
                """SELECT p.*, p.id AS profile_id, a.email, a.username, a.role,
                          a.email_verified, a.teamup_customer_id, a.teamup_status,
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
        "challengers": accts,
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
    req_invite_token = str(data.get("invite_token") or "").strip()
    if not _is_current_user_admin(db):
        existing_acct = db.execute(
            """SELECT p.id, p.client_name, a.role, a.password_hash, a.email, a.invite_token
               FROM challenge_profiles p
               LEFT JOIN challenge_user_accounts a ON a.profile_id = p.id
               WHERE LOWER(p.client_name)=LOWER(?) OR (? != '' AND LOWER(a.email)=LOWER(?))""",
            (cname, email, email),
        ).fetchone()
        if existing_acct:
            ex_role = (existing_acct["role"] or "").lower()
            ex_name = (existing_acct["client_name"] or "").strip().lower()
            valid_personal_invite = bool(req_invite_token and existing_acct["invite_token"] and req_invite_token == existing_acct["invite_token"])
            if ex_role == "admin" or ex_name in ("ewan (admin)", "ewan admin", "ewan taylor", "ewan t", "chris", "laura") or (existing_acct["password_hash"] and not valid_personal_invite):
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

    # Send verification email on account creation
    v_res = _send_verification_email(db, prof["id"], request.host_url.rstrip("/"))

    if data.get("auto_sign_in", True):
        _set_authenticated_session(prof, acct)

    try:
        auto_persist_profile_backup(db, prof["id"])
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "block": dict(block_row),
        "profile_id": prof["id"],
        "client_name": prof["client_name"],
        "username": acct["username"],
        "email": acct["email"],
        "email_verified": bool(acct.get("email_verified")),
        "verification_email_sent": v_res["sent"],
        "verification_url": v_res["verification_url"],
        "full_verification_url": v_res["full_verification_url"],
        "invite_url": f"/challenge/login?invite={acct['invite_token']}&email={acct['email']}",
        "message": (
            f"Account created for {prof['client_name']} (@{acct['username']})! Verification email sent to {acct['email']}."
            if v_res["sent"]
            else f"Account created for {prof['client_name']} (@{acct['username']})! Click the verification link sent for {acct['email']} to verify your email."
        ),
    })


@challenge_blocks_bp.route("/api/challenge/admin/teamup", methods=["GET", "POST"])
def api_challenge_admin_teamup():
    """Configure or inspect the TeamUp Gym Management integration (for future/live member & class sync)."""
    import base64
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    if request.method == "POST" and not _is_current_user_admin(db):
        return jsonify({"ok": False, "error": "Only Coach & Admin accounts can configure TeamUp."}), 403

    row = db.execute("SELECT * FROM teamup_integration_settings WHERE id=1").fetchone()
    curr = dict(row) if row else {}

    if request.method == "POST":
        data = request.get_json() or {}
        enabled = 1 if data.get("enabled", curr.get("enabled")) else 0
        provider_id = str(data.get("provider_id", curr.get("provider_id", ""))).strip()
        auto_block = str(data.get("auto_enroll_block_code", curr.get("auto_enroll_block_code", "CS-OCT2026"))).strip().upper()
        sync_classes = 1 if data.get("sync_class_attendance", curr.get("sync_class_attendance", 1)) else 0
        raw_key = str(data.get("api_key") or "").strip()
        api_key_set = 1 if raw_key else int(curr.get("api_key_set") or 0)
        api_key_b64 = base64.b64encode(raw_key.encode("utf-8")).decode("ascii") if raw_key else curr.get("api_key_b64", "")

        db.execute(
            """UPDATE teamup_integration_settings
               SET enabled=?, provider_id=?, api_key_set=?, api_key_b64=?,
                   auto_enroll_block_code=?, sync_class_attendance=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=1""",
            (enabled, provider_id, api_key_set, api_key_b64, auto_block, sync_classes),
        )
        if data.get("link_profile_id") and data.get("teamup_customer_id") is not None:
            lpid = int(data["link_profile_id"])
            tcid = str(data["teamup_customer_id"]).strip()
            db.execute(
                """UPDATE challenge_user_accounts
                   SET teamup_customer_id=?, teamup_status=?, updated_at=CURRENT_TIMESTAMP
                   WHERE profile_id=?""",
                (tcid, "Active Member" if tcid else "", lpid),
            )
        db.commit()
        row = db.execute("SELECT * FROM teamup_integration_settings WHERE id=1").fetchone()
        curr = dict(row)

    curr.pop("api_key_b64", None)
    curr["webhook_url"] = f"{request.host_url.rstrip('/')}/api/challenge/teamup/webhook"
    return jsonify({"ok": True, "teamup": curr})


@challenge_blocks_bp.route("/api/challenge/teamup/webhook", methods=["POST"])
def api_challenge_teamup_webhook():
    """Receive TeamUp Gym webhooks (new member enrollment or CS Fitness class check-in)."""
    from challenge import _upsert_checkin
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    data = request.get_json(silent=True) or {}
    event_type = (data.get("event") or data.get("type") or "customer.sync").strip().lower()
    email = (data.get("email") or (data.get("customer") or {}).get("email") or "").strip().lower()
    name = (data.get("name") or (data.get("customer") or {}).get("name") or "").strip()
    teamup_cid = str(data.get("teamup_customer_id") or data.get("customer_id") or (data.get("customer") or {}).get("id") or "").strip()

    t_cfg = db.execute("SELECT * FROM teamup_integration_settings WHERE id=1").fetchone()
    block_code = (data.get("block_code") or (t_cfg["auto_enroll_block_code"] if t_cfg else "CS-OCT2026")).strip().upper()
    block_row = db.execute(
        "SELECT * FROM challenge_blocks WHERE UPPER(invite_code)=? OR UPPER(block_code)=?",
        (block_code, block_code),
    ).fetchone() or db.execute("SELECT * FROM challenge_blocks WHERE status='Active' LIMIT 1").fetchone()

    db.execute(
        "UPDATE teamup_integration_settings SET last_webhook_at=?, updated_at=CURRENT_TIMESTAMP WHERE id=1",
        (datetime.now().strftime("%Y-%m-%d %H:%M"),),
    )

    if not email and not name:
        db.commit()
        return jsonify({"ok": False, "error": "TeamUp payload requires customer email or name."}), 400

    prof, acct = _upsert_challenger_for_block(
        db,
        {
            "client_name": name,
            "email": email,
            "username": data.get("username") or "",
            "teamup_customer_id": teamup_cid or f"TU-{secrets.token_hex(3).upper()}",
            "teamup_status": "Active Member (TeamUp)",
            "joined_via": "TeamUp Gym Sync",
            "start_weight_kg": data.get("start_weight_kg") or 80.0,
        },
        dict(block_row),
    )

    class_logged = None
    if "class_name" in data or "attendance" in event_type or "class" in event_type:
        cls_name = (data.get("class_name") or "CS Fitness Sweat").strip()
        date_str = (data.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
        is_cardio = any(k in cls_name.lower() for k in ("run", "sweat", "hyrox", "engine", "cardio", "conditioning"))
        new_t_type = "CARDIO" if is_cardio else "GYM"
        ex_ci = db.execute(
            "SELECT training_type, notes FROM daily_checkins WHERE profile_id=? AND date=?",
            (prof["id"], date_str),
        ).fetchone()
        ex_t = (ex_ci["training_type"] if ex_ci and ex_ci["training_type"] else "REST").upper()
        if ex_t in ("GYM & CARDIO", "BOTH") or (ex_t == "GYM" and new_t_type == "CARDIO") or (ex_t == "CARDIO" and new_t_type == "GYM"):
            merged_t_type = "GYM & CARDIO"
        else:
            merged_t_type = new_t_type
        ex_notes = (ex_ci["notes"] if ex_ci and ex_ci["notes"] else "").strip()
        tu_note = f"TeamUp: {cls_name}"
        merged_notes = f"{ex_notes} · {tu_note}" if (ex_notes and tu_note not in ex_notes) else (ex_notes or f"Synced from TeamUp ({cls_name})")
        _upsert_checkin(
            db,
            date_str,
            {"training_type": merged_t_type, "class_attended": f"TeamUp: {cls_name}", "notes": merged_notes},
            prof["id"],
        )
        class_logged = cls_name

    db.commit()
    return jsonify({
        "ok": True,
        "event": event_type,
        "profile_id": prof["id"],
        "client_name": prof["client_name"],
        "username": acct["username"],
        "email": acct["email"],
        "teamup_customer_id": acct.get("teamup_customer_id"),
        "class_logged": class_logged,
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
    from challenge import _get_profile_integrations, _update_profile_integrations
    pid = int(target_profile_id or payload.get("profile_id") or 1)
    counts = {
        "daily_checkins": 0,
        "daily_activities": 0,
        "workout_logs": 0,
        "weekly_submissions": 0,
        "progress_photos": 0,
        "daily_journey_moments": 0,
        "integrations": 0,
    }

    # Ensure profile exists (especially if a challenger > 1 is rehydrating after a container restart)
    prof_data = payload.get("profile") or {}
    if prof_data and isinstance(prof_data, dict):
        exists_prof = db.execute("SELECT id FROM challenge_profiles WHERE id=?", (pid,)).fetchone()
        sw = float(prof_data.get("start_weight_kg") or 80.0)
        tw = float(prof_data.get("target_weight_kg") or round(sw * 0.93, 1))
        sbf = float(prof_data.get("start_body_fat_pct") or 16.0)
        tbf = float(prof_data.get("target_body_fat_pct") or 14.0)
        sdate = str(prof_data.get("start_date") or prof_data.get("challenge_start") or "2026-10-19")[:10]
        goal_str = str(prof_data.get("goal") or "Weight Loss")
        ret_flag = bool(prof_data.get("returning_member"))
        calc = calculate_challenge_targets(
            start_weight_kg=sw,
            target_weight_kg=tw,
            start_body_fat_pct=sbf,
            target_body_fat_pct=tbf,
            protein_g=int(prof_data.get("target_protein_g") or 150),
            start_date=sdate,
            goal=goal_str,
            returning_member=ret_flag,
        )
        wk_json = prof_data.get("weekly_targets_json")
        if not wk_json:
            wk_json = json.dumps(prof_data.get("weekly_targets") or calc["weekly_targets"])
        elif not isinstance(wk_json, str):
            wk_json = json.dumps(wk_json)
        if not exists_prof:
            try:
                cname = (prof_data.get("client_name") or payload.get("client_name") or f"Challenger {pid}").strip()
                if pid == 1 and cname.lower() in ("ewan t", "ewan", "ewan taylor"):
                    cname = "Ewan Taylor"
                clash = db.execute("SELECT id FROM challenge_profiles WHERE LOWER(client_name)=LOWER(?) AND id!=?", (cname, pid)).fetchone()
                if clash:
                    cname = f"{cname} ({pid})"
                db.execute(
                    """INSERT INTO challenge_profiles (
                        id, client_name, goal, start_date, end_date,
                        start_weight_kg, target_weight_kg, start_body_fat_pct, target_body_fat_pct,
                        lean_body_mass_kg, fat_mass_kg, to_lose_kg,
                        target_calories, target_protein_g, target_fats_g, target_carbs_g,
                        target_fibre_g, target_water_l, target_sleep_hrs,
                        returning_member, workout_track, weekly_targets_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        pid,
                        cname,
                        calc["goal"],
                        calc["start_date"],
                        str(prof_data.get("end_date") or calc["end_date"])[:10],
                        calc["start_weight_kg"],
                        calc["target_weight_kg"],
                        calc["start_body_fat_pct"],
                        calc["target_body_fat_pct"],
                        float(prof_data.get("lean_body_mass_kg") or calc["lean_body_mass_kg"]),
                        float(prof_data.get("fat_mass_kg") or calc["fat_mass_kg"]),
                        float(prof_data.get("to_lose_kg") or calc["to_lose_kg"]),
                        int(prof_data.get("target_calories") or calc["target_calories"]),
                        int(prof_data.get("target_protein_g") or calc["target_protein_g"]),
                        int(prof_data.get("target_fats_g") or calc["target_fats_g"]),
                        int(prof_data.get("target_carbs_g") or calc["target_carbs_g"]),
                        int(prof_data.get("target_fibre_g") or 30),
                        float(prof_data.get("target_water_l") or calc["target_water_l"]),
                        8.0,
                        1 if ret_flag else 0,
                        str(prof_data.get("workout_track") or "mens"),
                        wk_json,
                    ),
                )
            except Exception:
                pass
        else:
            try:
                if pid == 1:
                    db.execute(
                        "UPDATE challenge_profiles SET client_name='Ewan Taylor', first_name='Ewan', last_name='Taylor' WHERE id=1"
                    )
                if prof_data.get("start_weight_kg"):
                    db.execute(
                        """UPDATE challenge_profiles SET
                            start_weight_kg=?, target_weight_kg=?, start_body_fat_pct=?, target_body_fat_pct=?,
                            lean_body_mass_kg=?, fat_mass_kg=?, to_lose_kg=?,
                            target_calories=?, target_protein_g=?, target_fats_g=?, target_carbs_g=?,
                            target_water_l=?, weekly_targets_json=?
                           WHERE id=?""",
                        (
                            calc["start_weight_kg"],
                            calc["target_weight_kg"],
                            calc["start_body_fat_pct"],
                            calc["target_body_fat_pct"],
                            calc["lean_body_mass_kg"],
                            calc["fat_mass_kg"],
                            calc["to_lose_kg"],
                            int(prof_data.get("target_calories") or calc["target_calories"]),
                            int(prof_data.get("target_protein_g") or calc["target_protein_g"]),
                            int(prof_data.get("target_fats_g") or calc["target_fats_g"]),
                            int(prof_data.get("target_carbs_g") or calc["target_carbs_g"]),
                            calc["target_water_l"],
                            wk_json,
                            pid,
                        ),
                    )
            except Exception:
                pass

    # Restore user account if present and missing
    acct_data = payload.get("user_account") or {}
    if acct_data and isinstance(acct_data, dict) and acct_data.get("username"):
        try:
            exists_acct = db.execute("SELECT profile_id FROM challenge_user_accounts WHERE profile_id=?", (pid,)).fetchone()
            if not exists_acct:
                restored_role = "challenger" if pid == 1 else (acct_data.get("role") or "challenger")
                db.execute(
                    """INSERT OR IGNORE INTO challenge_user_accounts
                       (profile_id, username, email, password_hash, role, email_verified)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        pid,
                        acct_data.get("username"),
                        acct_data.get("email") or "",
                        acct_data.get("password_hash") or "",
                        restored_role,
                        int(acct_data.get("email_verified") or 1),
                    ),
                )
        except Exception:
            pass

    # Restore Garmin & sync integrations
    integ_data = payload.get("integrations") or {}
    if integ_data and isinstance(integ_data, dict):
        try:
            curr_integ = _get_profile_integrations(db, pid, include_secrets=True)
            upd = {}
            for k in (
                "garmin_email",
                "garmin_password_set",
                "garmin_password_b64",
                "garmin_token_dump",
                "garmin_connected",
                "garmin_last_sync",
                "mfp_username",
                "nutrition_provider",
                "nutrition_connected",
                "nutrition_last_sync",
                "telegram_bot_token",
                "telegram_chat_id",
                "coach_telegram_handle",
                "coach_whatsapp_phone",
                "webhook_token",
            ):
                val = integ_data.get(k)
                if val not in (None, "", 0) or not curr_integ.get(k):
                    if val is not None and val != "":
                        upd[k] = val
            if upd.get("garmin_password_b64"):
                upd["garmin_password_set"] = 1
            if upd.get("garmin_token_dump"):
                upd["garmin_connected"] = 1
            if upd:
                _update_profile_integrations(db, pid, upd)
                counts["integrations"] = 1
        except Exception:
            pass

    for c in payload.get("daily_checkins", []):
        d_str = (c.get("date") or "")[:10]
        if not d_str:
            continue
        db.execute(
            """INSERT INTO daily_checkins (
                profile_id, date, weight_kg, weigh_time, training_type, class_attended,
                steps, protein_g, calories, carbs_g, fats_g, fibre_g, water_l,
                sleep_mins, sleep_str, sleep_score, body_battery, resting_hr,
                morning_steps_banked, checkpoint_12pm_5k, checkpoint_5pm_10k,
                caffeine_cutoff_met, electrolytes_taken, stick_to_plan,
                mindset_win, notes, sync_source_garmin, sync_source_nutrition
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(profile_id, date) DO UPDATE SET
                weight_kg=COALESCE(excluded.weight_kg, daily_checkins.weight_kg),
                weigh_time=CASE WHEN excluded.weigh_time != '' THEN excluded.weigh_time ELSE daily_checkins.weigh_time END,
                training_type=CASE WHEN excluded.training_type != '' AND excluded.training_type != 'REST' THEN excluded.training_type ELSE daily_checkins.training_type END,
                class_attended=CASE WHEN excluded.class_attended != '' THEN excluded.class_attended ELSE daily_checkins.class_attended END,
                steps=MAX(excluded.steps, COALESCE(daily_checkins.steps, 0)),
                protein_g=MAX(excluded.protein_g, COALESCE(daily_checkins.protein_g, 0)),
                calories=MAX(excluded.calories, COALESCE(daily_checkins.calories, 0)),
                carbs_g=CASE WHEN excluded.carbs_g > 0 THEN excluded.carbs_g ELSE daily_checkins.carbs_g END,
                fats_g=CASE WHEN excluded.fats_g > 0 THEN excluded.fats_g ELSE daily_checkins.fats_g END,
                fibre_g=CASE WHEN excluded.fibre_g > 0 THEN excluded.fibre_g ELSE daily_checkins.fibre_g END,
                water_l=CASE WHEN excluded.water_l > 0 THEN excluded.water_l ELSE daily_checkins.water_l END,
                sleep_mins=CASE WHEN excluded.sleep_mins > 0 THEN excluded.sleep_mins ELSE daily_checkins.sleep_mins END,
                sleep_str=CASE WHEN excluded.sleep_str != '' THEN excluded.sleep_str ELSE COALESCE(daily_checkins.sleep_str, '') END,
                sleep_score=COALESCE(excluded.sleep_score, daily_checkins.sleep_score),
                body_battery=COALESCE(excluded.body_battery, daily_checkins.body_battery),
                resting_hr=COALESCE(excluded.resting_hr, daily_checkins.resting_hr),
                morning_steps_banked=MAX(excluded.morning_steps_banked, COALESCE(daily_checkins.morning_steps_banked, 0)),
                checkpoint_12pm_5k=MAX(excluded.checkpoint_12pm_5k, COALESCE(daily_checkins.checkpoint_12pm_5k, 0)),
                checkpoint_5pm_10k=MAX(excluded.checkpoint_5pm_10k, COALESCE(daily_checkins.checkpoint_5pm_10k, 0)),
                caffeine_cutoff_met=MAX(excluded.caffeine_cutoff_met, COALESCE(daily_checkins.caffeine_cutoff_met, 0)),
                electrolytes_taken=MAX(excluded.electrolytes_taken, COALESCE(daily_checkins.electrolytes_taken, 0)),
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
                c.get("sleep_str") or "",
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

    try:
        for w in payload.get("workout_logs", []):
            db.execute(
                """INSERT INTO workout_logs (
                    profile_id, track, workout_num, week_num, row_key,
                    exercise_order, exercise_name, target_sets, target_reps,
                    weight_reps, set_logs_json, logged_date, notes
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(profile_id, track, workout_num, week_num, row_key) DO UPDATE SET
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
    except Exception:
        pass

    try:
        from challenge_progress import _ensure_weekly_submissions_table
        _ensure_weekly_submissions_table(db)
        for s in payload.get("weekly_submissions", []):
            w_num = int(s["week_num"]) if s.get("week_num") is not None else 0
            db.execute(
                """INSERT INTO weekly_submissions (
                       profile_id, week_num, challenger_comments, coach_feedback,
                       status, card_data_url, avg_weight_kg, avg_steps,
                       avg_calories, avg_protein_g, photos_count, submitted_at, reviewed_at
                   )
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(profile_id, week_num) DO UPDATE SET
                       challenger_comments=CASE WHEN excluded.challenger_comments != '' THEN excluded.challenger_comments ELSE weekly_submissions.challenger_comments END,
                       coach_feedback=CASE WHEN excluded.coach_feedback != '' THEN excluded.coach_feedback ELSE weekly_submissions.coach_feedback END,
                       status=CASE WHEN excluded.status != '' THEN excluded.status ELSE weekly_submissions.status END,
                       card_data_url=CASE WHEN excluded.card_data_url != '' THEN excluded.card_data_url ELSE COALESCE(weekly_submissions.card_data_url, '') END,
                       avg_weight_kg=COALESCE(excluded.avg_weight_kg, weekly_submissions.avg_weight_kg),
                       avg_steps=CASE WHEN excluded.avg_steps > 0 THEN excluded.avg_steps ELSE weekly_submissions.avg_steps END,
                       avg_calories=CASE WHEN excluded.avg_calories > 0 THEN excluded.avg_calories ELSE weekly_submissions.avg_calories END,
                       avg_protein_g=CASE WHEN excluded.avg_protein_g > 0 THEN excluded.avg_protein_g ELSE weekly_submissions.avg_protein_g END,
                       photos_count=CASE WHEN excluded.photos_count > 0 THEN excluded.photos_count ELSE weekly_submissions.photos_count END,
                       submitted_at=CASE WHEN excluded.submitted_at != '' THEN excluded.submitted_at ELSE weekly_submissions.submitted_at END,
                       reviewed_at=CASE WHEN excluded.reviewed_at != '' THEN excluded.reviewed_at ELSE weekly_submissions.reviewed_at END""",
                (
                    pid,
                    w_num,
                    s.get("challenger_comments") or "",
                    s.get("coach_feedback") or "",
                    s.get("status") or "Submitted",
                    s.get("card_data_url") or "",
                    s.get("avg_weight_kg"),
                    int(s.get("avg_steps") or 0),
                    int(s.get("avg_calories") or 0),
                    int(s.get("avg_protein_g") or 0),
                    int(s.get("photos_count") or 0),
                    s.get("submitted_at") or "",
                    s.get("reviewed_at") or "",
                ),
            )
            counts["weekly_submissions"] += 1
    except Exception:
        pass

    try:
        db.execute("DELETE FROM progress_photos WHERE profile_id=? AND (photo_data_url IS NULL OR photo_data_url='')", (pid,))
        for p in payload.get("progress_photos", []):
            if not p.get("photo_data_url"):
                continue
            w_num = int(p["week_num"]) if p.get("week_num") is not None else 0
            pose = p.get("pose") or "Front"
            exists = db.execute(
                "SELECT id FROM progress_photos WHERE profile_id=? AND week_num=? AND pose=?",
                (pid, w_num, pose),
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
                    (pid, w_num, pose, p.get("taken_date") or "2026-10-19", p.get("weight_kg"), p["photo_data_url"]),
                )
            counts["progress_photos"] += 1
    except Exception:
        pass

    try:
        for m in payload.get("daily_journey_moments", []):
            d_str = (m.get("date") or "")[:10]
            slot = m.get("slot") or "Breakfast"
            if not d_str or not m.get("photo_data_url"):
                continue
            db.execute(
                """INSERT INTO daily_journey_moments (profile_id, date, slot, caption, hashtags, photo_data_url)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(profile_id, date, slot) DO UPDATE SET
                       caption=CASE WHEN excluded.caption != '' THEN excluded.caption ELSE daily_journey_moments.caption END,
                       hashtags=CASE WHEN excluded.hashtags != '' THEN excluded.hashtags ELSE daily_journey_moments.hashtags END,
                       photo_data_url=CASE WHEN excluded.photo_data_url != '' THEN excluded.photo_data_url ELSE daily_journey_moments.photo_data_url END""",
                (pid, d_str, slot, m.get("caption") or "", m.get("hashtags") or "", m.get("photo_data_url") or ""),
            )
            counts["daily_journey_moments"] += 1
    except Exception:
        pass

    db.commit()
    try:
        auto_persist_profile_backup(db, pid)
    except Exception:
        pass
    return counts


def build_profile_backup_payload(db, pid=1, include_secrets=True):
    from challenge import _get_profile_integrations
    pid = int(pid or 1)
    prof_row = db.execute("SELECT * FROM challenge_profiles WHERE id=?", (pid,)).fetchone()
    prof = dict(prof_row) if prof_row else {"id": pid, "client_name": f"Challenger {pid}"}
    acct_row = None
    try:
        acct_row = db.execute(
            "SELECT profile_id, username, email, password_hash, role, email_verified FROM challenge_user_accounts WHERE profile_id=?",
            (pid,),
        ).fetchone()
    except Exception:
        pass
    payload = {
        "ok": True,
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "profile_id": pid,
        "client_name": prof.get("client_name", f"Challenger {pid}"),
        "profile": prof,
        "user_account": dict(acct_row) if acct_row else {},
        "integrations": _get_profile_integrations(db, pid, include_secrets=include_secrets),
        "daily_checkins": [dict(r) for r in db.execute("SELECT * FROM daily_checkins WHERE profile_id=? ORDER BY date", (pid,)).fetchall()],
        "workout_logs": [dict(r) for r in db.execute("SELECT * FROM workout_logs WHERE profile_id=? ORDER BY id", (pid,)).fetchall()],
        "progress_photos": [dict(r) for r in db.execute("SELECT * FROM progress_photos WHERE profile_id=? ORDER BY id", (pid,)).fetchall()],
    }
    for tbl in ("daily_activities", "weekly_submissions", "daily_journey_moments"):
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
        elif isinstance(val, dict):
            for col, v in list(val.items()):
                if col in ("created_at", "updated_at", "submitted_at", "reviewed_at") and v is not None:
                    val[col] = str(v)
    return payload


def auto_persist_profile_backup(db, pid=1):
    """Write a local JSON backup snapshot on every save so data survives process reloads."""
    import os
    from flask import current_app
    try:
        if current_app and current_app.config.get("TESTING"):
            return
    except Exception:
        pass
    try:
        pid = int(pid or 1)
        data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
        os.makedirs(data_dir, exist_ok=True)
        payload = build_profile_backup_payload(db, pid, include_secrets=True)
        backup_path = os.path.join(data_dir, f"backup_profile_{pid}.json")
        with open(backup_path, "w") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        pass


def _auto_seed_ewan_backup_if_empty(db):
    import glob
    import os
    from flask import current_app
    try:
        if current_app.config.get("TESTING"):
            return
        data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
        local_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))
        for bpath in sorted(glob.glob(os.path.join(data_dir, "backup_profile_*.json"))):
            try:
                with open(bpath, "r") as f:
                    bpayload = json.load(f)
                bpid = int(bpayload.get("profile_id") or 1)
                if bpid == 1 and abs(float((bpayload.get("profile") or {}).get("start_weight_kg") or 0) - 84.0) < 0.05:
                    bpayload.setdefault("profile", {})["start_weight_kg"] = 88.6
                _restore_backup_payload(db, bpayload, target_profile_id=bpid)
            except Exception:
                pass
        cnt = db.execute("SELECT COUNT(*) AS c FROM daily_checkins WHERE profile_id=1 AND date >= '2026-10-19'").fetchone()["c"]
        p1 = db.execute("SELECT client_name, start_weight_kg FROM challenge_profiles WHERE id=1").fetchone()
        sw1 = float(p1["start_weight_kg"]) if p1 and p1["start_weight_kg"] else 84.0
        cname1 = (p1["client_name"] or "") if p1 else ""
        wk3_fri = db.execute(
            "SELECT steps FROM daily_checkins WHERE profile_id=1 AND date='2026-11-06'"
        ).fetchone()
        wk3_fri_steps = int(wk3_fri["steps"] or 0) if wk3_fri else 0
        wk3_sub = db.execute(
            "SELECT challenger_comments FROM weekly_submissions WHERE profile_id=1 AND week_num=3"
        ).fetchone()
        has_wk3_comments = bool(wk3_sub and (wk3_sub["challenger_comments"] or "").strip())
        wk3_photos = db.execute(
            "SELECT COUNT(*) AS c FROM progress_photos WHERE profile_id=1 AND week_num=3 AND LENGTH(photo_data_url) > 100"
        ).fetchone()["c"]
        wk0_front = db.execute(
            "SELECT LENGTH(photo_data_url) AS plen FROM progress_photos WHERE profile_id=1 AND week_num=0 AND pose='Front'"
        ).fetchone()
        wk0_needs_crop = not wk0_front or int(wk0_front["plen"] or 0) > 35000 or int(wk0_front["plen"] or 0) < 1000
        if (
            cnt < 21
            or wk3_fri_steps < 1000
            or cname1 != "Ewan Taylor"
            or abs(sw1 - 84.0) < 0.05
            or not has_wk3_comments
            or wk3_photos < 3
            or wk0_needs_crop
        ):
            seed_path = os.path.join(data_dir, "ewan_seed_backup.json")
            if not os.path.exists(seed_path):
                seed_path = os.path.join(local_data_dir, "ewan_seed_backup.json")
            if os.path.exists(seed_path):
                with open(seed_path, "r") as f:
                    payload = json.load(f)
                _restore_backup_payload(db, payload, target_profile_id=1)
        db.execute(
            "UPDATE challenge_profiles SET client_name='Ewan Taylor', first_name='Ewan', last_name='Taylor' WHERE id=1"
        )
    except Exception:
        pass


@challenge_blocks_bp.route("/api/challenge/backup/export", methods=["GET"])
def api_challenge_backup_export():
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    prof = _get_active_profile(db)
    pid = int(request.args.get("profile_id") or prof["id"])
    if pid != int(prof["id"]) and not _is_current_user_admin(db):
        pid = int(prof["id"])
    payload = build_profile_backup_payload(db, pid, include_secrets=True)
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
    """Dedicated Coach & Admin Portal for Chris, Laura, and Ewan (taylor.ewan@googlemail.com)."""
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    if not _is_current_user_admin(db):
        return redirect(url_for("challenge_blocks.challenge_login_page", admin="1"))
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
           WHERE a.role='admin' OR LOWER(p.client_name) IN ('ewan (admin)', 'ewan admin', 'chris', 'laura')
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

    acct = db.execute(
        "SELECT username, email, role, invite_token, email_verified, teamup_customer_id, teamup_status FROM challenge_user_accounts WHERE profile_id=?",
        (profile["id"],),
    ).fetchone()
    profile["username"] = acct["username"] if acct else ""
    profile["email"] = acct["email"] if acct else ""
    profile["email_verified"] = bool(acct["email_verified"]) if acct and "email_verified" in acct.keys() else False
    profile["teamup_customer_id"] = acct["teamup_customer_id"] if acct and "teamup_customer_id" in acct.keys() else ""
    profile["teamup_status"] = acct["teamup_status"] if acct and "teamup_status" in acct.keys() else ""
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
            """SELECT p.*, COALESCE(a.email, '') AS email, COALESCE(a.username, '') AS username,
                      COALESCE(a.email_verified, 0) AS email_verified,
                      COALESCE(a.teamup_customer_id, '') AS teamup_customer_id,
                      COALESCE(a.teamup_status, '') AS teamup_status,
                      COALESCE(a.role, 'challenger') AS role,
                      e.block_id, COALESCE(b.name, 'Block 1 · Oct–Dec 2026') AS block_name,
                      COALESCE(b.invite_code, 'CS-OCT2026') AS invite_code
               FROM challenge_profiles p
               LEFT JOIN challenge_user_accounts a ON a.profile_id = p.id
               LEFT JOIN challenge_block_enrollments e ON e.profile_id = p.id
               LEFT JOIN challenge_blocks b ON b.id = e.block_id
               WHERE LOWER(p.client_name) NOT IN ('chris', 'laura', 'ewan (admin)', 'ewan admin')
                 AND COALESCE(a.role, 'challenger') != 'admin'
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
            "username": p.get("username") or "",
            "email": p["email"],
            "email_verified": bool(p.get("email_verified")),
            "teamup_customer_id": p.get("teamup_customer_id") or "",
            "teamup_status": p.get("teamup_status") or "",
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


@challenge_blocks_bp.route("/api/challenge/admin/invite-users", methods=["POST"])
def api_challenge_admin_invite_users():
    """Add one or more users (email addresses / names) to a Cohort Block after payment is processed.
    - New users receive a Welcome Email with a personal 'Set New Password & Day 1 Setup' link.
    - Returning users from a previous block keep their existing password and receive a 'Welcome Back — Access Unlocked' email.
    """
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    if not _is_current_user_admin(db):
        return jsonify({"ok": False, "error": "Only Coach & Admin accounts can invite users to a cohort block."}), 403

    data = request.get_json() or {}
    block_id = int(data.get("block_id") or 0)
    block_code = (data.get("block_code") or data.get("invite_code") or "").strip().upper()
    block_row = None
    if block_id:
        block_row = db.execute("SELECT * FROM challenge_blocks WHERE id=?", (block_id,)).fetchone()
    if not block_row and block_code:
        block_row = db.execute(
            "SELECT * FROM challenge_blocks WHERE UPPER(block_code)=? OR UPPER(invite_code)=?",
            (block_code, block_code),
        ).fetchone()
    if not block_row:
        block_row = db.execute("SELECT * FROM challenge_blocks WHERE status='Active' ORDER BY start_date DESC LIMIT 1").fetchone()
    block_dict = dict(block_row)

    # Support either structured `users` list, `entries` list, single fields, or bulk `emails_text` (one per line: `email, First Last`)
    raw_items = []
    for list_key in ("users", "entries"):
        if isinstance(data.get(list_key), list):
            for entry in data[list_key]:
                if isinstance(entry, dict):
                    raw_items.append(entry)
                elif isinstance(entry, str) and entry.strip():
                    parts = [p.strip() for p in re.split(r"[,;\t]+", entry.strip()) if p.strip()]
                    em = next((p for p in parts if "@" in p), "")
                    nm = next((p for p in parts if "@" not in p), "")
                    raw_items.append({"email": em, "client_name": nm})
    if data.get("emails_text"):
        for line in str(data["emails_text"]).splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in re.split(r"[,;\t]+", line) if p.strip()]
            em = next((p for p in parts if "@" in p), "")
            nm = next((p for p in parts if "@" not in p), "")
            raw_items.append({"email": em, "client_name": nm})
    if not raw_items and (data.get("email") or data.get("client_name") or data.get("first_name")):
        raw_items.append(data)

    if not raw_items:
        return jsonify({"ok": False, "error": "Please enter at least one email address or user name."}), 400

    base_url = request.host_url.rstrip("/")
    results = []
    for item in raw_items:
        em = (item.get("email") or "").strip().lower()
        existing_acct = None
        if em:
            existing_acct = db.execute(
                """SELECT a.*, p.client_name FROM challenge_user_accounts a
                   JOIN challenge_profiles p ON p.id = a.profile_id
                   WHERE LOWER(a.email)=?""",
                (em,),
            ).fetchone()
        was_existing_member = bool(existing_acct is not None)

        prof, acct = _upsert_challenger_for_block(
            db,
            {
                "email": em,
                "first_name": item.get("first_name") or "",
                "last_name": item.get("last_name") or "",
                "client_name": item.get("client_name") or item.get("name") or "",
                "age": item.get("age"),
                "start_weight_kg": item.get("start_weight_kg") or 80.0,
                "target_weight_kg": item.get("target_weight_kg"),
                "payment_ref": item.get("payment_ref") or data.get("payment_ref") or "Payment Confirmed",
                "joined_via": "Cohort Admin Invite",
                "returning_member": True if was_existing_member else bool(item.get("returning_member", False)),
                "onboarding_completed": False,
            },
            block_dict,
        )
        # Ensure new block enrollment starts with onboarding_completed=0 so 1st login prompts for starting photos & notes
        db.execute(
            """UPDATE challenge_block_enrollments
               SET onboarding_completed=0, welcome_email_sent=1
               WHERE block_id=? AND profile_id=?""",
            (block_dict["id"], prof["id"]),
        )
        if not was_existing_member and prof["id"] != 1:
            db.execute("UPDATE challenge_profiles SET onboarding_completed=0 WHERE id=?", (prof["id"],))
        db.commit()

        welcome_res = _send_block_welcome_email(
            db,
            prof["id"],
            block_dict,
            is_returning_user=was_existing_member,
            base_url=base_url,
        )
        results.append({
            "profile_id": prof["id"],
            "client_name": prof["client_name"],
            "first_name": prof.get("first_name") or "",
            "last_name": prof.get("last_name") or "",
            "email": acct["email"],
            "username": acct["username"],
            "is_returning": was_existing_member,
            "flow": "returning_block_access" if was_existing_member else "new_password_setup",
            "welcome_email_sent": welcome_res["sent"],
            "signup_url": welcome_res["welcome_url"],
            "welcome_url": welcome_res["welcome_url"],
            "full_welcome_url": welcome_res["full_welcome_url"],
        })

    return jsonify({
        "ok": True,
        "block": block_dict,
        "cohort_signup_url": f"{base_url}/challenge/login?code={block_dict['invite_code']}&signup=1",
        "count": len(results),
        "invited_count": len(results),
        "invited": results,
    })


@challenge_blocks_bp.route("/api/challenge/onboarding", methods=["GET", "POST"])
def api_challenge_first_login_onboarding():
    """Get or complete 1st-login Cohort Block setup (First/Last Name, Age, Start Weight, 3 Starting Photos, Initial Check-In Notes)."""
    from challenge_progress import _ensure_weekly_submissions_table
    db = get_db()
    ensure_blocks_and_auth_tables(db)
    _ensure_weekly_submissions_table(db)
    profile = _get_active_profile(db)
    pid = int(profile["id"])

    if request.method == "GET":
        w0_photos = [
            dict(r)
            for r in db.execute(
                "SELECT pose, weight_kg, taken_date, photo_data_url FROM progress_photos WHERE profile_id=? AND week_num=0",
                (pid,),
            ).fetchall()
        ]
        w0_sub = db.execute(
            "SELECT challenger_comments FROM weekly_submissions WHERE profile_id=? AND week_num=0",
            (pid,),
        ).fetchone()
        return jsonify({
            "ok": True,
            "profile_id": pid,
            "first_name": profile.get("first_name") or (profile.get("client_name") or "").split()[0],
            "last_name": profile.get("last_name") or "",
            "client_name": profile.get("client_name") or "",
            "age": profile.get("age"),
            "start_weight_kg": profile.get("start_weight_kg"),
            "target_weight_kg": profile.get("target_weight_kg"),
            "target_protein_g": profile.get("target_protein_g"),
            "target_calories": profile.get("target_calories"),
            "initial_checkin_notes": (
                profile.get("initial_checkin_notes")
                or (w0_sub["challenger_comments"] if w0_sub else "")
                or ""
            ),
            "onboarding_completed": bool(profile.get("onboarding_completed")),
            "starting_photos": w0_photos,
        })

    data = request.get_json() or {}
    first_name = (data.get("first_name") or profile.get("first_name") or "").strip()
    last_name = (data.get("last_name") or profile.get("last_name") or "").strip()
    cname = (data.get("client_name") or "").strip()
    if not cname and (first_name or last_name):
        # Preserve Ewan Taylor's exact canonical name if pid == 1
        cname = "Ewan Taylor" if pid == 1 else f"{first_name} {last_name}".strip()
    if not cname:
        cname = "Ewan Taylor" if pid == 1 else profile["client_name"]

    age_val = int(data["age"]) if str(data.get("age") or "").strip().isdigit() else profile.get("age")
    start_w = float(data.get("start_weight_kg") or profile.get("start_weight_kg") or 84.0)
    target_w = float(data.get("target_weight_kg") or profile.get("target_weight_kg") or round(start_w * 0.93, 1))
    prot_g = int(data.get("target_protein_g") or profile.get("target_protein_g") or 150)
    init_notes = (data.get("initial_checkin_notes") or "").strip()

    calc = calculate_challenge_targets(
        start_weight_kg=start_w,
        target_weight_kg=target_w,
        start_body_fat_pct=float(profile.get("start_body_fat_pct") or 16.0),
        target_body_fat_pct=float(profile.get("target_body_fat_pct") or 14.0),
        protein_g=prot_g,
        start_date=(profile.get("start_date") or "2026-10-19")[:10],
        goal=data.get("goal") or profile.get("goal") or "Weight Loss",
        returning_member=bool(profile.get("returning_member")),
    )

    db.execute(
        """UPDATE challenge_profiles SET
            client_name=?, first_name=?, last_name=?, age=?,
            initial_checkin_notes=?, onboarding_completed=1,
            start_weight_kg=?, target_weight_kg=?,
            lean_body_mass_kg=?, fat_mass_kg=?, to_lose_kg=?,
            target_calories=?, target_protein_g=?, target_fats_g=?, target_carbs_g=?,
            target_water_l=?, weekly_targets_json=?
           WHERE id=?""",
        (
            cname, first_name, last_name, age_val,
            init_notes,
            start_w, target_w,
            calc["lean_body_mass_kg"], calc["fat_mass_kg"], calc["to_lose_kg"],
            calc["target_calories"], prot_g, calc["target_fats_g"], calc["target_carbs_g"],
            calc["target_water_l"], json.dumps(calc["weekly_targets"]),
            pid,
        ),
    )
    db.execute(
        "UPDATE challenge_block_enrollments SET block_start_weight_kg=?, initial_checkin_notes=?, onboarding_completed=1 WHERE profile_id=?",
        (start_w, init_notes, pid),
    )
    # Also save initial_checkin_notes and start_w into Week 0 weekly_submissions
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    w0_photos_cnt = db.execute(
        "SELECT COUNT(*) AS c FROM progress_photos WHERE profile_id=? AND week_num=0 AND photo_data_url != ''",
        (pid,),
    ).fetchone()["c"]
    db.execute(
        """INSERT INTO weekly_submissions (profile_id, week_num, status, challenger_comments, avg_weight_kg, photos_count, submitted_at)
           VALUES (?, 0, 'Submitted', ?, ?, ?, ?)
           ON CONFLICT(profile_id, week_num) DO UPDATE SET
               challenger_comments=CASE WHEN excluded.challenger_comments != '' THEN excluded.challenger_comments ELSE weekly_submissions.challenger_comments END,
               avg_weight_kg=excluded.avg_weight_kg,
               photos_count=excluded.photos_count,
               updated_at=CURRENT_TIMESTAMP""",
        (pid, init_notes, start_w, w0_photos_cnt, now_str),
    )
    db.execute("UPDATE progress_photos SET weight_kg=? WHERE profile_id=? AND week_num=0", (start_w, pid))
    db.commit()
    try:
        auto_persist_profile_backup(db, pid)
    except Exception:
        pass
    updated_prof = _get_active_profile(db, pid)
    _set_authenticated_session(updated_prof)
    return jsonify({"ok": True, "profile": updated_prof, "onboarding_completed": True})




