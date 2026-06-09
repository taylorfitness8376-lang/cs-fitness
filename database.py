import sqlite3
import os
from flask import g, current_app


def get_db():
    if "db" not in g:
        path = current_app.config.get("DATABASE") or current_app.config["DATABASE_PATH"]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        g.db = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            coach_notes TEXT NOT NULL DEFAULT '',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    """)
    db.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
