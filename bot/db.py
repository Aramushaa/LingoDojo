import sqlite3
from pathlib import Path

import json
from datetime import date, datetime, timezone, timedelta
import math



REPO_ROOT = Path(__file__).resolve().parents[1]  # LingoDojo/
DATA_DIR = REPO_ROOT / "data"
DB_PATH = DATA_DIR / "app.db"
PACKS_DIR = DATA_DIR / "packs"

def get_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    

    # users
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        created_at TEXT,
        target_language TEXT NOT NULL DEFAULT 'it',
        ui_language TEXT NOT NULL DEFAULT 'en',
        helper_language TEXT DEFAULT NULL
    )
    """)


    # packs metadata
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS packs (
        pack_id TEXT PRIMARY KEY,
        target_language TEXT NOT NULL,
        level TEXT,
        title TEXT NOT NULL,
        description TEXT
    )
    """)

    # items inside a pack
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pack_items (
        item_id INTEGER PRIMARY KEY AUTOINCREMENT,
        pack_id TEXT NOT NULL,
        term TEXT NOT NULL,
        chunk TEXT NOT NULL,
        translation_en TEXT,
        note TEXT,
        FOREIGN KEY (pack_id) REFERENCES packs(pack_id)
    )
    """)

    # which packs a user activated
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_packs (
        user_id INTEGER NOT NULL,
        pack_id TEXT NOT NULL,
        activated_at TEXT,
        PRIMARY KEY (user_id, pack_id),
        FOREIGN KEY (user_id) REFERENCES users(user_id),
        FOREIGN KEY (pack_id) REFERENCES packs(pack_id)
    )
    """)

    # super-simple session storage (so bot knows what the user is doing right now)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_session (
        user_id INTEGER PRIMARY KEY,
        mode TEXT NOT NULL,
        item_id INTEGER,
        stage TEXT NOT NULL,
        meta_json TEXT,
        updated_at TEXT NOT NULL
    )
    """)


    # spaced repetition reviews
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        user_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        status TEXT NOT NULL,              -- new | learning | mature
        interval_days INTEGER NOT NULL,    -- days until next review
        due_date TEXT NOT NULL,            -- YYYY-MM-DD
        last_reviewed_at TEXT,             -- ISO timestamp
        reps INTEGER NOT NULL DEFAULT 0,   -- number of successful reviews
        lapses INTEGER NOT NULL DEFAULT 0, -- number of failures
        PRIMARY KEY (user_id, item_id)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lexicon_cache_it (
        term TEXT PRIMARY KEY,
        data_json TEXT NOT NULL,
        fetched_at TEXT NOT NULL
    )
    """)


    def _ensure_column(conn, table: str, col: str, coltype: str):
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cur.fetchall()]
        if col not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
            conn.commit()

    _ensure_column(conn, "user_session", "meta_json", "TEXT")




    def _add_column_if_missing(cursor, table: str, column: str, col_def: str):
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cursor.fetchall()]
        if column not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
    
    _add_column_if_missing(cursor, "users", "target_language", "TEXT NOT NULL DEFAULT 'it'")
    _add_column_if_missing(cursor, "users", "ui_language", "TEXT NOT NULL DEFAULT 'en'")
        # --- reviews undo support ---
    _add_column_if_missing(cursor, "reviews", "prev_status", "TEXT")
    _add_column_if_missing(cursor, "reviews", "prev_interval_days", "INTEGER")
    _add_column_if_missing(cursor, "reviews", "prev_due_date", "TEXT")
    _add_column_if_missing(cursor, "reviews", "prev_last_reviewed_at", "TEXT")
    _add_column_if_missing(cursor, "reviews", "prev_reps", "INTEGER")
    _add_column_if_missing(cursor, "reviews", "prev_lapses", "INTEGER")
    _add_column_if_missing(cursor, "reviews", "undo_available", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(cursor, "users", "helper_language", "TEXT DEFAULT NULL")





    conn.commit()
    conn.close()

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_user_languages(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT target_language, ui_language FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row  # (target_language, ui_language) or None


def import_packs_from_folder():
    """
    Loads all JSON packs from data/packs into SQLite.
    Safe to run multiple times (won't duplicate packs).
    """
    conn = get_connection()
    cursor = conn.cursor()

    PACKS_DIR.mkdir(parents=True, exist_ok=True)

    for pack_file in PACKS_DIR.glob("*.json"):
        with open(pack_file, "r", encoding="utf-8") as f:
            pack = json.load(f)

        pack_id = pack["pack_id"]
        target_language = pack["target_language"]
        level = pack.get("level")
        title = pack["title"]
        description = pack.get("description")

        # Insert pack metadata (ignore if exists)
        cursor.execute("""
            INSERT OR IGNORE INTO packs (pack_id, target_language, level, title, description)
            VALUES (?, ?, ?, ?, ?)
        """, (pack_id, target_language, level, title, description))

        # If items already exist for this pack, skip inserting items again
        cursor.execute("SELECT COUNT(*) FROM pack_items WHERE pack_id = ?", (pack_id,))
        (count_existing,) = cursor.fetchone()
        if count_existing > 0:
            continue

        # Insert items
        for item in pack["items"]:
            cursor.execute("""
                INSERT INTO pack_items (pack_id, term, chunk, translation_en, note)
                VALUES (?, ?, ?, ?, ?)
            """, (
                pack_id,
                item["term"],
                item["chunk"],
                item.get("translation_en"),
                item.get("note", "")
            ))

    conn.commit()
    conn.close()

def list_packs(target_language: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pack_id, level, title, description
        FROM packs
        WHERE target_language = ?
        ORDER BY level, title
    """, (target_language,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def activate_pack(user_id: int, pack_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO user_packs (user_id, pack_id, activated_at)
        VALUES (?, ?, ?)
    """, (user_id, pack_id, utc_now_iso()))
    conn.commit()
    conn.close()

def get_user_active_packs(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pack_id FROM user_packs WHERE user_id = ?
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

def pick_one_item_from_pack(pack_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT item_id, term, chunk, translation_en, note
        FROM pack_items
        WHERE pack_id = ?
        ORDER BY RANDOM()
        LIMIT 1
    """, (pack_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def set_session(user_id: int, mode: str, item_id: int | None, stage: str, meta: dict | None = None):
    conn = get_connection()
    cursor = conn.cursor()

    meta_json = json.dumps(meta or {}, ensure_ascii=False)

    cursor.execute("""
        INSERT INTO user_session (user_id, mode, item_id, stage, meta_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            mode=excluded.mode,
            item_id=excluded.item_id,
            stage=excluded.stage,
            meta_json=excluded.meta_json,
            updated_at=excluded.updated_at
    """, (user_id, mode, item_id, stage, meta_json, utc_now_iso()))

    conn.commit()
    conn.close()

def get_session(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT mode, item_id, stage, meta_json FROM user_session WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    mode, item_id, stage, meta_json = row

    try:
        meta = json.loads(meta_json) if meta_json else {}
    except Exception:
        meta = {}

    return mode, item_id, stage, meta

def clear_session(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_session WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_item_by_id(item_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT item_id, term, chunk, translation_en, note
        FROM pack_items
        WHERE item_id = ?
    """, (item_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def set_user_target_language(user_id: int, target_language: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET target_language = ? WHERE user_id = ?",
        (target_language, user_id)
    )
    conn.commit()
    conn.close()

def set_user_ui_language(user_id: int, ui_language: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET ui_language = ? WHERE user_id = ?",
        (ui_language, user_id)
    )
    conn.commit()
    conn.close()


def today_str() -> str:
    return date.today().isoformat()  # "2026-01-26"


def ensure_review_row(user_id: int, item_id: int):
    """
    Make sure an item exists in the user's review queue.
    If it doesn't exist, create it as 'new' due today.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO reviews (user_id, item_id, status, interval_days, due_date, last_reviewed_at, reps, lapses)
        VALUES (?, ?, 'new', 0, ?, NULL, 0, 0)
    """, (user_id, item_id, today_str()))
    conn.commit()
    conn.close()

def get_due_item(user_id: int):
    """
    Return one item_id that is due today (or overdue), else None.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT item_id
        FROM reviews
        WHERE user_id = ? AND due_date <= ?
        ORDER BY due_date ASC
        LIMIT 1
    """, (user_id, today_str()))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_review_state(user_id: int, item_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT status, interval_days, due_date, reps, lapses
        FROM reviews
        WHERE user_id = ? AND item_id = ?
    """, (user_id, item_id))
    row = cursor.fetchone()
    conn.close()
    return row

def apply_grade(user_id: int, item_id: int, grade: str):
    """
    grade: 'good' | 'hard' | 'again'
    Minimal scheduling:
      - good  -> interval grows, due moves forward
      - again -> interval resets, due today (repeat soon)
    """
    state = get_review_state(user_id, item_id)
    if not state:
        ensure_review_row(user_id, item_id)
        state = get_review_state(user_id, item_id)

    status, interval_days, due_date, reps, lapses = state

    # Save "previous state" for Undo
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE reviews
        SET
            prev_status = ?,
            prev_interval_days = ?,
            prev_due_date = ?,
            prev_last_reviewed_at = last_reviewed_at,
            prev_reps = ?,
            prev_lapses = ?,
            undo_available = 1
        WHERE user_id = ? AND item_id = ?
    """, (status, interval_days, due_date, reps, lapses, user_id, item_id))
    conn.commit()
    conn.close()


    if grade == "good":
        # good -> grows fast (double)
        new_interval = 1 if interval_days < 1 else interval_days * 2
        new_reps = reps + 1
        new_lapses = lapses
        new_status = "learning"
        if new_reps >= 5 and new_interval >= 16:
            new_status = "mature"
        new_due = (date.today() + timedelta(days=new_interval)).isoformat()

    elif grade == "hard":
        # hard -> grows slower than good
        # 0 -> 1, 1 -> 2, 2 -> 3, 4 -> 6, 8 -> 12 ...
        new_interval = 1 if interval_days < 1 else max(1, math.ceil(interval_days * 1.5))
        new_reps = reps + 1
        new_lapses = lapses
        new_status = "learning"
        if new_reps >= 6 and new_interval >= 20:
            new_status = "mature"
        new_due = (date.today() + timedelta(days=new_interval)).isoformat()

    else:  # again
        new_interval = 1
        new_reps = reps
        new_lapses = lapses + 1
        new_status = "learning"
        new_due = date.today().isoformat()


    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE reviews
        SET status = ?, interval_days = ?, due_date = ?, last_reviewed_at = ?, reps = ?, lapses = ?
        WHERE user_id = ? AND item_id = ?
    """, (new_status, new_interval, new_due, utc_now_iso(), new_reps, new_lapses, user_id, item_id))
    conn.commit()
    conn.close()

    return new_status, new_interval, new_due

def undo_last_grade(user_id: int, item_id: int):
    """
    Restores the previous review state if undo is available.
    Returns (status, interval_days, due_date) after undo, or None if not possible.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            undo_available,
            prev_status, prev_interval_days, prev_due_date,
            prev_last_reviewed_at, prev_reps, prev_lapses
        FROM reviews
        WHERE user_id = ? AND item_id = ?
    """, (user_id, item_id))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    (
        undo_available,
        prev_status, prev_interval_days, prev_due_date,
        prev_last_reviewed_at, prev_reps, prev_lapses
    ) = row

    if int(undo_available or 0) != 1 or prev_status is None:
        conn.close()
        return None

    # Restore previous values
    cursor.execute("""
        UPDATE reviews
        SET
            status = ?,
            interval_days = ?,
            due_date = ?,
            last_reviewed_at = ?,
            reps = ?,
            lapses = ?,
            -- Clear undo snapshot so it can't be spammed repeatedly
            prev_status = NULL,
            prev_interval_days = NULL,
            prev_due_date = NULL,
            prev_last_reviewed_at = NULL,
            prev_reps = NULL,
            prev_lapses = NULL,
            undo_available = 0
        WHERE user_id = ? AND item_id = ?
    """, (
        prev_status, prev_interval_days, prev_due_date,
        prev_last_reviewed_at, prev_reps, prev_lapses,
        user_id, item_id
    ))

    conn.commit()

    cursor.execute("""
        SELECT status, interval_days, due_date
        FROM reviews
        WHERE user_id = ? AND item_id = ?
    """, (user_id, item_id))
    restored = cursor.fetchone()
    conn.close()

    return restored  # (status, interval_days, due_date)


def get_due_count(user_id: int) -> int:
    """How many items are due today (or overdue) for this user?"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*)
        FROM reviews
        WHERE user_id = ? AND due_date <= ?
    """, (user_id, date.today().isoformat()))
    (count,) = cursor.fetchone()
    conn.close()
    return int(count)

def get_status_counts(user_id: int) -> dict:
    """Return counts grouped by status: new/learning/mature."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT status, COUNT(*)
        FROM reviews
        WHERE user_id = ?
        GROUP BY status
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()

    # default 0 for missing statuses
    out = {"new": 0, "learning": 0, "mature": 0}
    for status, cnt in rows:
        if status in out:
            out[status] = int(cnt)
    return out

def get_lexicon_cache_it(term: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT data_json FROM lexicon_cache_it WHERE term = ?", (term,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return json.loads(row[0])

def set_lexicon_cache_it(term: str, data: dict):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO lexicon_cache_it(term, data_json, fetched_at) VALUES(?,?,?)",
        (term, json.dumps(data, ensure_ascii=False), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

def get_user_profile(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT target_language, ui_language, helper_language FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()
    return row  # (target, ui, helper) or None


def set_user_helper_language(user_id: int, helper_language: str | None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET helper_language = ? WHERE user_id = ?",
        (helper_language, user_id)
    )
    conn.commit()
    conn.close()


def toggle_pack(user_id: int, pack_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM user_packs WHERE user_id=? AND pack_id=?", (user_id, pack_id))
    exists = cur.fetchone() is not None

    if exists:
        cur.execute("DELETE FROM user_packs WHERE user_id=? AND pack_id=?", (user_id, pack_id))
    else:
        cur.execute(
            "INSERT OR IGNORE INTO user_packs (user_id, pack_id, activated_at) VALUES (?, ?, ?)",
            (user_id, pack_id, utc_now_iso())
        )

    conn.commit()
    conn.close()
    return (not exists)


def pick_one_item_for_user(user_id: int, target_language: str):
    """
    Picks a random item from ANY active pack of the user (filtered by target_language).
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT pi.item_id, pi.term, pi.chunk, pi.translation_en, pi.note
        FROM pack_items pi
        JOIN packs p ON p.pack_id = pi.pack_id
        JOIN user_packs up ON up.pack_id = p.pack_id
        WHERE up.user_id = ? AND p.target_language = ?
        ORDER BY RANDOM()
        LIMIT 1
    """, (user_id, target_language))
    row = cur.fetchone()
    conn.close()
    return row
