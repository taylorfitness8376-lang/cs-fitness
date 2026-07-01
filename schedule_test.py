"""
CS Fitness — Schedule / Publish Cycle Tester
Run from Terminal:  python3 schedule_test.py

Simulates a week of calendar scheduling and publishing against a throwaway
temp database (never touches data/gym.db), then walks through several days
printing what the TV display would actually show on each day. Use this to
validate schedule/publish behaviour without waiting for a real day to pass.
"""

import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ.setdefault("FLASK_SKIP_DOTENV", "1")

import app as flask_app
from database import init_db, get_db


def setup_temp_app():
    db_fd, db_path = tempfile.mkstemp()
    flask_app.app.config.update({"TESTING": True, "DATABASE": db_path, "SECRET_KEY": "test"})
    ctx = flask_app.app.app_context()
    ctx.push()
    init_db()
    return ctx, db_fd, db_path


def teardown_temp_app(ctx, db_fd, db_path):
    ctx.pop()
    os.close(db_fd)
    os.unlink(db_path)


def make_session(db, name):
    cur = db.execute("INSERT INTO sessions (name, coach_notes) VALUES (?, '')", (name,))
    db.commit()
    return cur.lastrowid


def show_for_day(label, day):
    with patch("app.datetime") as mock_dt:
        mock_dt.now.return_value = datetime.combine(day, datetime.min.time()).replace(hour=9)
        mock_dt.strftime = datetime.strftime
        result = flask_app.get_current_session()
    name = result["name"] if result else "(nothing scheduled)"
    print(f"  {label:<22} {day.strftime('%a %Y-%m-%d')}  ->  TV shows: {name}")


def main():
    ctx, db_fd, db_path = setup_temp_app()
    try:
        db = get_db()
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)

        mon = make_session(db, "Monday Strength")
        tue = make_session(db, "Tuesday Conditioning")
        wed = make_session(db, "Wednesday Mobility")

        print("\n1) Loading calendar for the week (one session per day)...")
        db.execute("INSERT OR REPLACE INTO calendar (date, session_id) VALUES (?, ?)",
                   (yesterday.isoformat(), mon))
        db.execute("INSERT OR REPLACE INTO calendar (date, session_id) VALUES (?, ?)",
                   (today.isoformat(), tue))
        db.execute("INSERT OR REPLACE INTO calendar (date, session_id) VALUES (?, ?)",
                   (tomorrow.isoformat(), wed))
        db.commit()

        print("\n2) Before any 'Publish Now' click, calendar drives the display:")
        show_for_day("yesterday", yesterday)
        show_for_day("today", today)
        show_for_day("tomorrow", tomorrow)

        print("\n3) Gym owner clicks 'Publish Now' on yesterday's session (as often happens"
              " when kicking off a workout manually)...")
        yesterday_set_at = datetime.combine(yesterday, datetime.min.time()).replace(hour=8)
        db.execute("UPDATE override SET session_id=?, set_at=? WHERE id=1",
                   (mon, yesterday_set_at.strftime("%Y-%m-%d %H:%M:%S")))
        db.commit()
        show_for_day("yesterday (published)", yesterday)

        print("\n4) Cycling forward through the following days WITHOUT clicking 'Clear"
              " Override' — this is what the gym owner is seeing:")
        show_for_day("today", today)
        show_for_day("tomorrow", tomorrow)

        print("\nCheck:")
        print("  'today' and 'tomorrow' should show their own calendar sessions (Tuesday")
        print("  Conditioning / Wednesday Mobility), NOT 'Monday Strength'. If you see")
        print("  'Monday Strength' repeated for today/tomorrow, the override-expiry fix")
        print("  in get_current_session() (app.py) has regressed.")
    finally:
        teardown_temp_app(ctx, db_fd, db_path)


if __name__ == "__main__":
    main()
