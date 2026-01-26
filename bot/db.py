import sqlite3
from pathlib import Path

import json
from datetime import datetime, timezone


# Path to database file
DB_PATH = Path("data/app.db")

# Directory containing pack JSON files
PACKS_DIR = Path("data/packs")

def get_connection():
    """
    Opens a connection to the SQLite database.
    If the file does not exist, SQLite will create it.
    """
    return sqlite3.connect(DB_PATH)

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
        ui_language TEXT NOT NULL DEFAULT 'en'
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
        updated_at TEXT
    )
    """)

    def _add_column_if_missing(cursor, table: str, column: str, col_def: str):
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cursor.fetchall()]
        if column not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
    
    _add_column_if_missing(cursor, "users", "target_language", "TEXT NOT NULL DEFAULT 'it'")
    _add_column_if_missing(cursor, "users", "ui_language", "TEXT NOT NULL DEFAULT 'en'")



    conn.commit()
    conn.close()



def utc_now_iso():
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

def set_session(user_id: int, mode: str, item_id: int | None, stage: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_session (user_id, mode, item_id, stage, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            mode=excluded.mode,
            item_id=excluded.item_id,
            stage=excluded.stage,
            updated_at=excluded.updated_at
    """, (user_id, mode, item_id, stage, utc_now_iso()))
    conn.commit()
    conn.close()

def get_session(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT mode, item_id, stage FROM user_session WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row  # (mode, item_id, stage) or None

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
