import sqlite3
import json
import os
import time
from pathlib import Path

DB_PATH = Path(os.getenv("LEARNING_DB_PATH", str(Path(__file__).parent / "data" / "learning.db")))


def get_connection():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profile (
                id INTEGER PRIMARY KEY DEFAULT 1,
                background TEXT NOT NULL DEFAULT '',
                explanation_styles TEXT NOT NULL DEFAULT '[]',
                detail_level TEXT NOT NULL DEFAULT 'standard',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sources TEXT NOT NULL DEFAULT '[]',
                journal TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _parse_json(value: str, default):
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def get_profile() -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
        if not row:
            return None
        d = dict(row)
        d["explanation_styles"] = _parse_json(d["explanation_styles"], [])
        return d
    finally:
        conn.close()


def save_profile(background: str, explanation_styles: list[str], detail_level: str):
    now = int(time.time() * 1000)
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO profile (id, background, explanation_styles, detail_level, created_at, updated_at)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                background=excluded.background,
                explanation_styles=excluded.explanation_styles,
                detail_level=excluded.detail_level,
                updated_at=excluded.updated_at
        """, (background, json.dumps(explanation_styles), detail_level, now, now))
        conn.commit()
    finally:
        conn.close()


def get_all_topics() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM topics ORDER BY created_at DESC").fetchall()
    finally:
        conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["sources"] = _parse_json(d["sources"], [])
        d["journal"] = _parse_json(d["journal"], {})
        result.append(d)
    return result


def get_topic(topic_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    d = dict(row)
    d["sources"] = _parse_json(d["sources"], [])
    d["journal"] = _parse_json(d["journal"], {})
    return d


def create_topic(name: str) -> int:
    now = int(time.time() * 1000)
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO topics (name, sources, journal, created_at, updated_at) VALUES (?, '[]', '{}', ?, ?)",
            (name, now, now)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def add_sources(topic_id: int, new_sources: list[dict]):
    topic = get_topic(topic_id)
    if not topic:
        return
    existing = topic["sources"]
    existing.extend(new_sources)
    now = int(time.time() * 1000)
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE topics SET sources = ?, updated_at = ? WHERE id = ?",
            (json.dumps(existing), now, topic_id)
        )
        conn.commit()
    finally:
        conn.close()


def save_journal(topic_id: int, journal: dict):
    now = int(time.time() * 1000)
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE topics SET journal = ?, updated_at = ? WHERE id = ?",
            (json.dumps(journal), now, topic_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_topic(topic_id: int):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
        conn.commit()
    finally:
        conn.close()
