import pytest
from database import init_db, get_db

def test_schema_creates_all_tables(app):
    with app.app_context():
        db = get_db()
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {row["name"] for row in tables}
        assert {"sessions", "blocks", "exercises", "schedule", "override"} <= names

def test_override_row_seeded(app):
    with app.app_context():
        db = get_db()
        row = db.execute("SELECT * FROM override WHERE id=1").fetchone()
        assert row is not None
        assert row["session_id"] is None
