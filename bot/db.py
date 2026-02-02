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
        helper_language TEXT DEFAULT NULL,
        user_level TEXT DEFAULT 'A1'
    )
    """)


    # packs metadata
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS packs (
        pack_id TEXT PRIMARY KEY,
        target_language TEXT NOT NULL,
        level TEXT,
        title TEXT NOT NULL,
        description TEXT,
        pack_type TEXT,
        chunk_size INTEGER,
        missions_enabled INTEGER
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





    def _add_column_if_missing(cursor, table: str, column: str, col_def: str):
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cursor.fetchall()]
        if column not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
    
    _add_column_if_missing(cursor, "users", "target_language", "TEXT NOT NULL DEFAULT 'it'")
    _add_column_if_missing(cursor, "users", "ui_language", "TEXT NOT NULL DEFAULT 'en'")
    _add_column_if_missing(cursor, "users", "learn_since_scene", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(cursor, "packs", "pack_type", "TEXT")
    _add_column_if_missing(cursor, "packs", "chunk_size", "INTEGER")
    _add_column_if_missing(cursor, "packs", "missions_enabled", "INTEGER")
        # --- reviews undo support ---
    _add_column_if_missing(cursor, "reviews", "prev_status", "TEXT")
    _add_column_if_missing(cursor, "reviews", "prev_interval_days", "INTEGER")
    _add_column_if_missing(cursor, "reviews", "prev_due_date", "TEXT")
    _add_column_if_missing(cursor, "reviews", "prev_last_reviewed_at", "TEXT")
    _add_column_if_missing(cursor, "reviews", "prev_reps", "INTEGER")
    _add_column_if_missing(cursor, "reviews", "prev_lapses", "INTEGER")
    _add_column_if_missing(cursor, "reviews", "undo_available", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(cursor, "users", "helper_language", "TEXT DEFAULT NULL")
    _add_column_if_missing(cursor, "pack_items", "level", "TEXT")
    _add_column_if_missing(cursor, "pack_items", "category", "TEXT")
    _add_column_if_missing(cursor, "pack_items", "tags_json", "TEXT")
    _add_column_if_missing(cursor, "pack_items", "cultural_note", "TEXT")
    _add_column_if_missing(cursor, "pack_items", "pronunciation_text", "TEXT")
    _add_column_if_missing(cursor, "pack_items", "translation_helper", "TEXT")
    # --- pack_items: holographic card fields (backward-compatible) ---
    _add_column_if_missing(cursor, "pack_items", "focus", "TEXT")              # word | phrase
    _add_column_if_missing(cursor, "pack_items", "lemma", "TEXT")              # if focus=word
    _add_column_if_missing(cursor, "pack_items", "phrase", "TEXT")             # if focus=phrase
    _add_column_if_missing(cursor, "pack_items", "phrase_hint", "TEXT")        # optional suggested chunk
    _add_column_if_missing(cursor, "pack_items", "register", "TEXT")
    _add_column_if_missing(cursor, "pack_items", "risk", "TEXT")
    _add_column_if_missing(cursor, "pack_items", "trap", "TEXT")
    _add_column_if_missing(cursor, "pack_items", "native_sauce", "TEXT")
    _add_column_if_missing(cursor, "pack_items", "components_json", "TEXT")
    _add_column_if_missing(cursor, "pack_items", "media_json", "TEXT")
    _add_column_if_missing(cursor, "pack_items", "drills_json", "TEXT")
    _add_column_if_missing(cursor, "pack_items", "source_uid", "TEXT")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pack_items_source_uid ON pack_items(pack_id, source_uid)")


    # --- NEW: contexts table (multiple contexts per card) ---
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS card_contexts (
        context_id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL,
        lang TEXT NOT NULL DEFAULT 'it',
        sentence TEXT NOT NULL,
        source TEXT,
        FOREIGN KEY (item_id) REFERENCES pack_items(item_id) ON DELETE CASCADE
    )
    """)


    # --- NEW: scenes table (roleplay scenes per pack) ---
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pack_scenes (
        scene_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
        pack_id TEXT NOT NULL,
        scene_id TEXT NOT NULL,
        unlock_rule_json TEXT,
        roleplay_json TEXT,
        FOREIGN KEY (pack_id) REFERENCES packs(pack_id) ON DELETE CASCADE,
        UNIQUE(pack_id, scene_id)
    )
    """)

    # --- NEW: AI cache (reduce quota) ---
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_cache (
        cache_key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)






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


def ai_cache_get(cache_key: str) -> dict | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT value_json FROM ai_cache WHERE cache_key = ?", (cache_key,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def ai_cache_set(cache_key: str, value: dict):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO ai_cache (cache_key, value_json, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET
            value_json=excluded.value_json,
            created_at=excluded.created_at
    """, (cache_key, json.dumps(value, ensure_ascii=False), utc_now_iso()))
    conn.commit()
    conn.close()


def get_learn_since_scene(user_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT learn_since_scene FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return int(row[0]) if row and row[0] is not None else 0


def set_learn_since_scene(user_id: int, value: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET learn_since_scene = ? WHERE user_id = ?", (int(value), user_id))
    conn.commit()
    conn.close()


def import_packs_from_folder():
    """
    Loads all JSON packs from data/packs into SQLite.
    Supports:
      - legacy schema: { items: [...] }
      - v2 mission schema: { cards: [...], scenes: [...] }
    """
    conn = get_connection()
    cursor = conn.cursor()

    PACKS_DIR.mkdir(parents=True, exist_ok=True)

    # Load all pack files first so we can clean up removed packs
    packs = []
    for path in PACKS_DIR.glob("*.json"):
        with open(path, "r", encoding="utf-8") as f:
            pack = json.load(f)
            packs.append(pack)

    # Remove packs that no longer exist on disk
    pack_ids_in_files = {p.get("pack_id") for p in packs if p.get("pack_id")}
    if pack_ids_in_files:
        cursor.execute(
            "SELECT pack_id FROM packs WHERE pack_id NOT IN ({})".format(
                ",".join("?" for _ in pack_ids_in_files)
            ),
            tuple(pack_ids_in_files),
        )
        stale = [r[0] for r in cursor.fetchall()]
        if stale:
            cursor.execute(
                "DELETE FROM pack_items WHERE pack_id IN ({})".format(
                    ",".join("?" for _ in stale)
                ),
                tuple(stale),
            )
            cursor.execute(
                "DELETE FROM pack_scenes WHERE pack_id IN ({})".format(
                    ",".join("?" for _ in stale)
                ),
                tuple(stale),
            )
            cursor.execute(
                "DELETE FROM user_packs WHERE pack_id IN ({})".format(
                    ",".join("?" for _ in stale)
                ),
                tuple(stale),
            )
            cursor.execute(
                "DELETE FROM packs WHERE pack_id IN ({})".format(
                    ",".join("?" for _ in stale)
                ),
                tuple(stale),
            )

    for pack in packs:
        pack_id = pack["pack_id"]
        target_language = pack.get("target_language", "it")
        level = pack.get("level")
        title = pack.get("title", pack_id)
        description = pack.get("description", "")
        pack_type = pack.get("pack_type")
        chunk_size = pack.get("chunk_size")
        missions_enabled = pack.get("missions_enabled")

        # Infer pack type if not provided
        if not pack_type:
            cards = pack.get("cards") or []
            if cards:
                phrase_count = sum(1 for c in cards if (c.get("focus") or "").lower() == "phrase")
                pack_type = "phrase" if phrase_count >= max(1, len(cards) // 2) else "word"
            else:
                pack_type = "word"

        if chunk_size is None and pack_type == "phrase":
            chunk_size = 5
        if missions_enabled is None:
            missions_enabled = 1 if pack_type == "phrase" else 0

        # Upsert pack metadata
        cursor.execute("""
            INSERT INTO packs (pack_id, target_language, level, title, description, pack_type, chunk_size, missions_enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(pack_id) DO UPDATE SET
                target_language=excluded.target_language,
                level=excluded.level,
                title=excluded.title,
                description=excluded.description,
                pack_type=excluded.pack_type,
                chunk_size=excluded.chunk_size,
                missions_enabled=excluded.missions_enabled
        """, (pack_id, target_language, level, title, description, pack_type, chunk_size, missions_enabled))

        # --------- Import legacy items OR v2 cards ---------
        cards = pack.get("cards")
        items = pack.get("items")

        def _safe_json(x):
            return json.dumps(x, ensure_ascii=False) if x is not None else None

        if cards:
            for c in cards:
                focus = c.get("focus", "word")  # word | phrase

                lemma = c.get("lemma")
                phrase = c.get("phrase")
                phrase_hint = c.get("phrase_hint")

                # Backward-compatible "term" and "chunk" (what Learn expects)
                if focus == "phrase":
                    term = phrase or (phrase_hint or "")
                    chunk = phrase or (phrase_hint or term)
                else:
                    term = lemma or ""
                    chunk = phrase_hint or term

                meaning_en = c.get("meaning_en") or c.get("translation_en")
                meaning_helper = c.get("meaning_helper") or c.get("translation_helper")

                meta = c.get("meta") or {}
                tags = meta.get("tags") or []
                components = c.get("components") or []

                source_uid = c.get("source_uid") or c.get("id") or c.get("card_id") or ""
                if not source_uid:
                    source_uid = f"{term}\n{chunk}".strip()

                cursor.execute("""
                    INSERT OR IGNORE INTO pack_items (
                        pack_id, source_uid, term, chunk, translation_en, note,
                        focus, lemma, phrase, phrase_hint,
                        level, category, register, risk,
                        trap, native_sauce, cultural_note,
                        tags_json, components_json, media_json, drills_json,
                        translation_helper, pronunciation_text
                    )
                    VALUES (?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?)
                """, (
                    pack_id,
                    source_uid,
                    term,
                    chunk,
                    meaning_en,
                    "",

                    focus,
                    lemma,
                    phrase,
                    phrase_hint,

                    c.get("level", level),
                    meta.get("category"),
                    meta.get("register"),
                    meta.get("risk"),

                    meta.get("trap"),
                    meta.get("native_sauce"),
                    meta.get("cultural_note"),

                    _safe_json(tags),
                    _safe_json(components),
                    _safe_json(c.get("media") or {}),
                    _safe_json(c.get("drills") or {}),

                    meaning_helper,
                    c.get("pronunciation_text") or chunk or term
                ))

                if cursor.rowcount == 0:
                    continue

                item_id = cursor.lastrowid

                # Context sentences
                for sent in (c.get("contexts_it") or []):
                    cursor.execute("""
                        INSERT INTO card_contexts (item_id, lang, sentence, source)
                        VALUES (?, 'it', ?, ?)
                    """, (item_id, sent, (c.get("context_source") or None)))

        elif items:
            # legacy packs: keep your current schema but store extra fields if present
            for item in items:
                tags = item.get("tags") or []
                source_uid = item.get("source_uid") or item.get("id") or item.get("card_id")
                if not source_uid:
                    source_uid = f"{item.get('term','')}\n{(item.get('chunk') or item.get('term',''))}".strip()

                cursor.execute("""
                    INSERT OR IGNORE INTO pack_items (
                        pack_id, source_uid, term, chunk, translation_en, note,
                        level, category, tags_json, cultural_note,
                        pronunciation_text, translation_helper,
                        focus, lemma, phrase
                    )
                    VALUES (?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?,
                            'word', ?, NULL)
                """, (
                    pack_id,
                    source_uid,
                    item["term"],
                    item.get("chunk") or item["term"],
                    item.get("translation_en"),
                    item.get("note", ""),

                    item.get("level", level),
                    item.get("category"),
                    json.dumps(tags, ensure_ascii=False),
                    item.get("cultural_note"),

                    item.get("pronunciation_text", item.get("chunk") or item["term"]),
                    item.get("translation_helper"),

                    item.get("term")
                ))

        # --------- Import scenes (optional) ---------
        for s in (pack.get("scenes") or []):
            cursor.execute("""
                INSERT INTO pack_scenes (pack_id, scene_id, unlock_rule_json, roleplay_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(pack_id, scene_id) DO UPDATE SET
                    unlock_rule_json=excluded.unlock_rule_json,
                    roleplay_json=excluded.roleplay_json
            """, (
                pack_id,
                s.get("scene_id"),
                _safe_json(s.get("unlock_rule") or {}),
                _safe_json(s.get("roleplay") or {})
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


def get_pack_info(pack_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pack_id, level, title, description, pack_type, chunk_size, missions_enabled, target_language
        FROM packs
        WHERE pack_id = ?
    """, (pack_id,))
    row = cursor.fetchone()
    conn.close()
    return row

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
        SELECT item_id, term, chunk, translation_en, note, pack_id, focus
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
    Skips and cleans stale review rows that point to missing pack_items.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # loop until we find a valid item or run out
    while True:
        cursor.execute("""
            SELECT item_id
            FROM reviews
            WHERE user_id = ? AND due_date <= ?
            ORDER BY due_date ASC
            LIMIT 1
        """, (user_id, today_str()))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        item_id = row[0]
        cursor.execute("SELECT 1 FROM pack_items WHERE item_id = ?", (item_id,))
        if cursor.fetchone():
            conn.close()
            return item_id

        # stale review row -> delete and continue
        cursor.execute("DELETE FROM reviews WHERE user_id = ? AND item_id = ?", (user_id, item_id))
        conn.commit()


def get_due_item_in_pack(user_id: int, pack_id: str):
    """
    Return one due item_id from a specific pack.
    """
    conn = get_connection()
    cursor = conn.cursor()

    while True:
        cursor.execute("""
            SELECT r.item_id
            FROM reviews r
            JOIN pack_items pi ON pi.item_id = r.item_id
            WHERE r.user_id = ? AND r.due_date <= ? AND pi.pack_id = ?
            ORDER BY r.due_date ASC
            LIMIT 1
        """, (user_id, today_str(), pack_id))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        item_id = row[0]
        cursor.execute("SELECT 1 FROM pack_items WHERE item_id = ?", (item_id,))
        if cursor.fetchone():
            conn.close()
            return item_id

        cursor.execute("DELETE FROM reviews WHERE user_id = ? AND item_id = ?", (user_id, item_id))
        conn.commit()

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


def mark_item_mature(user_id: int, item_id: int):
    """
    Mark item as mature with a long interval so it won't appear again soon.
    """
    # Ensure row exists first
    ensure_review_row(user_id, item_id)

    new_status = "mature"
    new_interval = 3650  # ~10 years
    new_due = (date.today() + timedelta(days=new_interval)).isoformat()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE reviews
        SET status = ?, interval_days = ?, due_date = ?, last_reviewed_at = ?, reps = reps + 1
        WHERE user_id = ? AND item_id = ?
    """, (new_status, new_interval, new_due, utc_now_iso(), user_id, item_id))
    conn.commit()
    conn.close()

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


def _cleanup_stale_reviews(conn, user_id: int):
    """
    Remove reviews that point to missing pack_items or inactive packs.
    """
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM reviews
        WHERE user_id = ?
          AND item_id NOT IN (
            SELECT pi.item_id
            FROM pack_items pi
            JOIN user_packs up ON up.pack_id = pi.pack_id
            WHERE up.user_id = ?
          )
    """, (user_id, user_id))
    conn.commit()


def get_due_count(user_id: int) -> int:
    """How many items are due today (or overdue) for this user (active packs only)."""
    conn = get_connection()
    _cleanup_stale_reviews(conn, user_id)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*)
        FROM reviews r
        JOIN pack_items pi ON pi.item_id = r.item_id
        JOIN user_packs up ON up.pack_id = pi.pack_id
        WHERE r.user_id = ? AND up.user_id = ? AND r.due_date <= ?
    """, (user_id, user_id, date.today().isoformat()))
    (count,) = cursor.fetchone()
    conn.close()
    return int(count)

def get_status_counts(user_id: int) -> dict:
    """Return counts grouped by status for active packs only."""
    conn = get_connection()
    _cleanup_stale_reviews(conn, user_id)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.status, COUNT(*)
        FROM reviews r
        JOIN pack_items pi ON pi.item_id = r.item_id
        JOIN user_packs up ON up.pack_id = pi.pack_id
        WHERE r.user_id = ? AND up.user_id = ?
        GROUP BY r.status
    """, (user_id, user_id))
    rows = cursor.fetchall()
    conn.close()

    # default 0 for missing statuses
    out = {"new": 0, "learning": 0, "mature": 0}
    for status, cnt in rows:
        if status in out:
            out[status] = int(cnt)
    return out


def get_random_meanings_from_active_packs(user_id: int, target_language: str, exclude_item_id: int, limit: int = 2) -> list[str]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT pi.translation_en
        FROM pack_items pi
        JOIN user_packs up ON up.pack_id = pi.pack_id
        JOIN packs p ON p.pack_id = pi.pack_id
        WHERE up.user_id = ?
          AND p.target_language = ?
          AND pi.item_id != ?
          AND pi.translation_en IS NOT NULL
          AND TRIM(pi.translation_en) != ''
        ORDER BY RANDOM()
        LIMIT ?
    """, (user_id, target_language, exclude_item_id, limit))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows if r and r[0]]


def get_random_meanings_from_pack(pack_id: str, exclude_item_id: int, limit: int = 2) -> list[str]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT translation_en
        FROM pack_items
        WHERE pack_id = ?
          AND item_id != ?
          AND translation_en IS NOT NULL
          AND TRIM(translation_en) != ''
        ORDER BY RANDOM()
        LIMIT ?
    """, (pack_id, exclude_item_id, limit))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows if r and r[0]]

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
    Picks one random item from active packs, filtered by user level.
    """
    user_level = get_user_level(user_id)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT pi.item_id, pi.term, pi.chunk, pi.translation_en, pi.note, pi.pack_id, pi.focus
        FROM pack_items pi
        JOIN packs p ON p.pack_id = pi.pack_id
        JOIN user_packs up ON up.pack_id = p.pack_id
        WHERE up.user_id = ?
          AND p.target_language = ?
          AND (pi.level IS NULL OR pi.level = '' OR pi.level <= ?)
        ORDER BY RANDOM()
        LIMIT 1
    """, (user_id, target_language, user_level))
    row = cur.fetchone()
    conn.close()
    return row


def get_user_level(user_id: int) -> str:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_level FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return (row[0] if row and row[0] else "A1")


def set_user_level(user_id: int, level: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET user_level = ? WHERE user_id = ?", (level, user_id))
    conn.commit()
    conn.close()


def get_active_items_total(user_id: int, target_language: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM pack_items pi
        JOIN packs p ON p.pack_id = pi.pack_id
        JOIN user_packs up ON up.pack_id = p.pack_id
        WHERE up.user_id = ?
          AND p.target_language = ?
    """, (user_id, target_language))
    (cnt,) = cur.fetchone()
    conn.close()
    return int(cnt)


def get_active_items_introduced(user_id: int, target_language: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT pi.item_id)
        FROM reviews r
        JOIN pack_items pi ON pi.item_id = r.item_id
        JOIN packs p ON p.pack_id = pi.pack_id
        JOIN user_packs up ON up.pack_id = p.pack_id
        WHERE r.user_id = ?
          AND up.user_id = ?
          AND p.target_language = ?
    """, (user_id, user_id, target_language))
    (cnt,) = cur.fetchone()
    conn.close()
    return int(cnt)


def pick_next_new_item_for_user(user_id: int, target_language: str):
    """
    Pick the next *not-yet-introduced* item from active packs in a stable order.
    Stable order MVP:
      - pack level, pack title (so A1 packs first)
      - then pack_items.item_id (import order)
    """
    user_level = get_user_level(user_id)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT pi.item_id, pi.term, pi.chunk, pi.translation_en, pi.note, pi.pack_id, pi.focus
        FROM pack_items pi
        JOIN packs p ON p.pack_id = pi.pack_id
        JOIN user_packs up ON up.pack_id = p.pack_id
        WHERE up.user_id = ?
          AND p.target_language = ?
          AND (p.level IS NULL OR p.level = '' OR p.level <= ?)
          AND NOT EXISTS (
              SELECT 1 FROM reviews r
              WHERE r.user_id = ? AND r.item_id = pi.item_id
          )
        ORDER BY
          COALESCE(p.level, 'Z') ASC,
          p.title ASC,
          pi.item_id ASC
        LIMIT 1
    """, (user_id, target_language, user_level, user_id))

    row = cur.fetchone()
    conn.close()
    return row


def pick_next_new_item_for_user_in_pack(user_id: int, pack_id: str):
    """
    Pick the next *not-yet-introduced* item from a specific pack.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT pi.item_id, pi.term, pi.chunk, pi.translation_en, pi.note, pi.pack_id, pi.focus
        FROM pack_items pi
        WHERE pi.pack_id = ?
          AND NOT EXISTS (
              SELECT 1 FROM reviews r
              WHERE r.user_id = ? AND r.item_id = pi.item_id
          )
        ORDER BY pi.item_id ASC
        LIMIT 1
    """, (pack_id, user_id))
    row = cur.fetchone()
    conn.close()
    return row


def get_pack_item_counts(user_id: int, pack_id: str) -> tuple[int, int]:
    """
    Return (total_items, introduced_items) for a specific pack.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM pack_items
        WHERE pack_id = ?
    """, (pack_id,))
    (total,) = cur.fetchone()

    cur.execute("""
        SELECT COUNT(DISTINCT pi.item_id)
        FROM reviews r
        JOIN pack_items pi ON pi.item_id = r.item_id
        WHERE r.user_id = ? AND pi.pack_id = ?
    """, (user_id, pack_id))
    (introduced,) = cur.fetchone()
    conn.close()
    return int(total or 0), int(introduced or 0)

def get_random_context_for_item(item_id: int, lang: str = "it") -> str | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT sentence
        FROM card_contexts
        WHERE item_id = ? AND lang = ?
        ORDER BY RANDOM()
        LIMIT 1
    """, (item_id, lang))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def get_item_holographic_meta(item_id: int) -> dict:
    """
    Returns a dict of holographic fields for Learn deconstruct + drills.
    Safe defaults if missing.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            register,
            risk,
            trap,
            native_sauce,
            cultural_note,
            tags_json,
            drills_json,
            media_json
        FROM pack_items
        WHERE item_id = ?
    """, (item_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return {
            "register": None,
            "risk": "safe",
            "trap": None,
            "native_sauce": None,
            "cultural_note": None,
            "tags": [],
            "drills": {},
            "media": {},
        }

    register, risk, trap, native_sauce, cultural_note, tags_json, drills_json, media_json = row

    try:
        tags = json.loads(tags_json) if tags_json else []
    except Exception:
        tags = []

    try:
        drills = json.loads(drills_json) if drills_json else {}
    except Exception:
        drills = {}

    try:
        media = json.loads(media_json) if media_json else {}
    except Exception:
        media = {}

    return {
        "register": register,
        "risk": risk or "safe",
        "trap": trap,
        "native_sauce": native_sauce,
        "cultural_note": cultural_note,
        "tags": tags,
        "drills": drills,
        "media": media,
    }

def reset_user_learning_progress(user_id: int, target_language: str = "it"):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM reviews
        WHERE user_id = ?
          AND item_id IN (
            SELECT pi.item_id
            FROM pack_items pi
            JOIN packs p ON p.pack_id = pi.pack_id
            WHERE p.target_language = ?
          )
    """, (user_id, target_language))
    conn.commit()
    conn.close()

def get_pack_id_for_item(item_id: int) -> str | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT pack_id FROM pack_items WHERE item_id = ?", (item_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def pick_one_scene_for_pack(pack_id: str) -> dict | None:
    """
    Returns one random scene for a pack as dict:
    { scene_id, unlock_rule, roleplay }
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT scene_id, unlock_rule_json, roleplay_json
        FROM pack_scenes
        WHERE pack_id = ?
        ORDER BY RANDOM()
        LIMIT 1
    """, (pack_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    scene_id, unlock_json, roleplay_json = row

    try:
        unlock = json.loads(unlock_json) if unlock_json else {}
    except Exception:
        unlock = {}

    try:
        roleplay = json.loads(roleplay_json) if roleplay_json else {}
    except Exception:
        roleplay = {}

    return {"scene_id": scene_id, "unlock_rule": unlock, "roleplay": roleplay}

def pick_one_scene_for_user_active_packs(user_id: int) -> dict | None:
    """
    Pick one random scene among all scenes belonging to packs the user activated.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT ps.pack_id, ps.scene_id, ps.unlock_rule_json, ps.roleplay_json
        FROM pack_scenes ps
        JOIN user_packs up ON up.pack_id = ps.pack_id
        WHERE up.user_id = ?
        ORDER BY RANDOM()
        LIMIT 1
    """, (user_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    pack_id, scene_id, unlock_json, roleplay_json = row

    try:
        unlock = json.loads(unlock_json) if unlock_json else {}
    except Exception:
        unlock = {}

    try:
        roleplay = json.loads(roleplay_json) if roleplay_json else {}
    except Exception:
        roleplay = {}

    return {"pack_id": pack_id, "scene_id": scene_id, "unlock_rule": unlock, "roleplay": roleplay}
