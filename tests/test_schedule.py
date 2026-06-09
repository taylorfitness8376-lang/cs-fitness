from unittest.mock import patch
from datetime import datetime
from database import get_db


def seed_sessions(db):
    db.execute("INSERT INTO sessions (id, name, coach_notes) VALUES (1, 'Session A', '')")
    db.execute("INSERT INTO sessions (id, name, coach_notes) VALUES (2, 'Session B', '')")
    db.commit()


def test_returns_correct_slot_for_time_of_day(app):
    with app.app_context():
        db = get_db()
        seed_sessions(db)
        # Monday 06:00 = A, Monday 18:00 = B
        db.execute("INSERT INTO schedule (day_of_week, start_time, session_id) VALUES (0,'06:00',1)")
        db.execute("INSERT INTO schedule (day_of_week, start_time, session_id) VALUES (0,'18:00',2)")
        db.commit()

        from app import get_current_session
        # 09:00 Monday → Session A (06:00 slot is last passed)
        with patch("app.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 8, 9, 0)
            result = get_current_session()
        assert result["name"] == "Session A"

        # 17:59 Monday → still Session A (18:00 slot not yet active)
        with patch("app.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 8, 17, 59)
            result = get_current_session()
        assert result["name"] == "Session A"

        # 18:00 Monday → Session B (slot starts exactly now)
        with patch("app.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 8, 18, 0)
            result = get_current_session()
        assert result["name"] == "Session B"


def test_walks_back_to_previous_day(app):
    with app.app_context():
        db = get_db()
        seed_sessions(db)
        # Only Monday 18:00 scheduled; check Tuesday 05:00 → should return Monday's slot
        db.execute("INSERT INTO schedule (day_of_week, start_time, session_id) VALUES (0,'18:00',1)")
        db.commit()

        from app import get_current_session
        with patch("app.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 9, 5, 0)  # Tuesday 05:00
            result = get_current_session()
        assert result["name"] == "Session A"


def test_override_wins_over_schedule(app):
    with app.app_context():
        db = get_db()
        seed_sessions(db)
        db.execute("INSERT INTO schedule (day_of_week, start_time, session_id) VALUES (0,'06:00',1)")
        db.execute("UPDATE override SET session_id=2 WHERE id=1")
        db.commit()

        from app import get_current_session
        with patch("app.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 8, 9, 0)
            result = get_current_session()
        assert result["name"] == "Session B"


def test_returns_none_when_no_schedule(app):
    with app.app_context():
        from app import get_current_session
        with patch("app.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 8, 9, 0)
            result = get_current_session()
        assert result is None
