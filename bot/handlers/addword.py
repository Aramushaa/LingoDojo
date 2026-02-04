from __future__ import annotations

from typing import List
import json
import re
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

from bot.utils.telegram import get_chat_sender
from bot.services.dictionary_it import validate_it_term
from bot.services.lexicon_it import get_or_fetch_lexicon_it
from bot.services.ai_feedback import generate_word_card, generate_phrase_scenario, generate_learn_feedback, generate_sentence_upgrade, generate_conjugation
from bot.services.validation import validate_sentence
from bot.services.tts_edge import tts_it
from bot.db import (
    get_user_profile,
    get_user_level,
    set_session,
    get_session,
    clear_session,
    ensure_my_words_pack,
    upsert_my_word_item,
    upsert_card_context,
    ensure_review_row,
    list_my_words_categories,
    list_my_words_in_category,
    list_my_words_search,
    list_my_words_all,
    rename_my_words_category,
)

CATEGORIES = [
    "Verbs",
    "Travel",
    "Food & Drink",
    "Shopping",
    "Daily Life",
    "Work & Study",
    "Emotions",
    "Time & Dates",
    "Politeness",
    "General",
]


def h(text: str) -> str:
    return escape(text or "")


async def _safe_answer(query):
    try:
        await query.answer()
    except BadRequest:
        return


def _next_level(level: str) -> str:
    order = ["A1", "A2", "B1", "B2", "C1", "C2"]
    lvl = (level or "A1").upper()
    if lvl not in order:
        return "A2"
    idx = order.index(lvl)
    return order[min(idx + 1, len(order) - 1)]


def _parse_terms(text: str, limit: int = 10) -> List[str]:
    raw = (text or "").replace(";", ",").replace("\n", ",")
    terms = [t.strip() for t in raw.split(",") if t.strip()]
    # de-dupe while preserving order
    seen = set()
    out = []
    for t in terms:
        if t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append(t)
    return out[:limit]


def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "term"


def _is_phrase(term: str) -> bool:
    return len((term or "").split()) > 1


def _suggest_categories(term: str) -> List[str]:
    t = (term or "").lower()
    out = []
    if any(t.endswith(suf) for suf in ("are", "ere", "ire")):
        out.append("Verbs")
    if any(k in t for k in ("aeroporto", "volo", "hotel", "treno", "biglietto", "gate")):
        out.append("Travel")
    if any(k in t for k in ("caffè", "pane", "vino", "acqua", "ristorante", "bar")):
        out.append("Food & Drink")
    if any(k in t for k in ("comprare", "prezzo", "sconto", "negozio")):
        out.append("Shopping")
    if any(k in t for k in ("per favore", "scusi", "mi può")):
        out.append("Politeness")
    if not out:
        out.append("General")
    return out[:3]


def _normalize_categories(suggestions: List[str] | None, fallback_term: str) -> List[str]:
    if suggestions:
        allowed = {c.lower(): c for c in CATEGORIES}
        out = []
        for s in suggestions:
            if not s:
                continue
            key = s.strip().lower()
            if key in allowed and allowed[key] not in out:
                out.append(allowed[key])
        if out:
            return out[:4]
    return _suggest_categories(fallback_term)


def _word_card_text(card: dict, helper_lang: str | None) -> str:
    term = card.get("term") or ""
    meaning_en = card.get("meaning_en") or "-"
    meaning_helper = card.get("meaning_helper") or "-"
    senses = card.get("senses") or []
    examples = card.get("examples") or []

    lines = [
        f"🧩 <b>WORD</b>: <b>{h(term)}</b>",
        f"EN: {h(meaning_en)}",
    ]
    if helper_lang:
        lines.append(f"FA: {h(meaning_helper)}")

    if senses:
        lines.append("\nMeanings:")
        for i, s in enumerate(senses[:3], 1):
            s_en = s.get("meaning_en") or ""
            s_h = s.get("meaning_helper") or ""
            usage = s.get("usage") or ""
            line = f"{i}) {h(s_en)}"
            if helper_lang and s_h:
                line += f" — {h(s_h)}"
            if usage:
                line += f" ({h(usage)})"
            lines.append(line)

    if examples:
        lines.append("\nIT examples:")
        for ex in examples[:3]:
            it = ex.get("it") or ""
            en = ex.get("en") or ""
            ha = ex.get("helper") or ""
            line = f"• {h(it)}"
            if en:
                line += f"   —   {h(en)}"
            if helper_lang and ha:
                line += f"   —   {h(ha)}"
            lines.append(line)

    return "\n\n".join(lines)


def _phrase_card_text(card: dict, helper_lang: str | None) -> str:
    term = card.get("term") or ""
    meaning_en = card.get("meaning_en") or "-"
    meaning_helper = card.get("meaning_helper") or "-"
    senses = card.get("senses") or []
    examples = card.get("examples") or []

    lines = [
        f"🧩 <b>PHRASE</b>: <b>{h(term)}</b>",
        f"EN: {h(meaning_en)}",
    ]
    if helper_lang:
        lines.append(f"FA: {h(meaning_helper)}")

    if senses:
        lines.append("\nMeanings:")
        for i, s in enumerate(senses[:3], 1):
            s_en = s.get("meaning_en") or ""
            s_h = s.get("meaning_helper") or ""
            usage = s.get("usage") or ""
            line = f"{i}) {h(s_en)}"
            if helper_lang and s_h:
                line += f" — {h(s_h)}"
            if usage:
                line += f" ({h(usage)})"
            lines.append(line)

    if examples:
        lines.append("\nIT examples:")
        for ex in examples[:3]:
            it = ex.get("it") or ""
            en = ex.get("en") or ""
            ha = ex.get("helper") or ""
            line = f"• {h(it)}"
            if en:
                line += f" — {h(en)}"
            if helper_lang and ha:
                line += f" — {h(ha)}"
            lines.append(line)

    return "\n".join(lines)


def _card_keyboard(has_next: bool, is_phrase: bool) -> InlineKeyboardMarkup:
    row1 = [
        InlineKeyboardButton("✅ Save", callback_data="ADDWORD|SAVE"),
        InlineKeyboardButton("🎯 Learn", callback_data="ADDWORD|LEARN"),
    ]
    row2 = [
        InlineKeyboardButton("🧠 Grammar", callback_data="ADDWORD|GRAMMAR"),
        InlineKeyboardButton("🌶 Culture", callback_data="ADDWORD|CULTURE"),
    ]
    row3 = []
    if not is_phrase:
        row3.append(InlineKeyboardButton("🧾 Conjugations", callback_data="ADDWORD|CONJ"))
    row3.append(InlineKeyboardButton("🏷 Categories", callback_data="ADDWORD|CATS"))
    row4 = [
        InlineKeyboardButton("🔊 Pronounce", callback_data="ADDWORD|PRON"),
        InlineKeyboardButton("⏭ Next", callback_data="ADDWORD|NEXT") if has_next else InlineKeyboardButton("❌ Cancel", callback_data="ADDWORD|CANCEL"),
    ]
    rows = [row1, row2, row3, row4]
    return InlineKeyboardMarkup(rows)


def _category_keyboard(suggestions: List[str]) -> InlineKeyboardMarkup:
    rows = []
    for cat in suggestions:
        rows.append([InlineKeyboardButton(f"✅ {cat}", callback_data=f"ADDWORD|CAT|{cat}")])
    rows.append([InlineKeyboardButton("⏭ Skip", callback_data="ADDWORD|CAT|SKIP")])
    return InlineKeyboardMarkup(rows)


def _mywords_menu(pack_id: str) -> tuple[str, InlineKeyboardMarkup]:
    categories = list_my_words_categories(pack_id)
    lines = ["🗂 <b>My Words</b>"]
    kb = []
    if not categories:
        lines.append("No saved words yet.")
        kb.append([InlineKeyboardButton("➕ Add words", callback_data="home:add")])
        return "\n".join(lines), InlineKeyboardMarkup(kb)

    total = sum(c[1] for c in categories)
    lines.append(f"Total: <b>{total}</b>")
    lines.append("Choose an action:")
    kb.append([InlineKeyboardButton("📂 Categories", callback_data="MYWORDS|CATS")])
    kb.append([InlineKeyboardButton("📜 Show all", callback_data="MYWORDS|ALL")])
    kb.append([InlineKeyboardButton("🔎 Search", callback_data="MYWORDS|SEARCH")])
    kb.append([InlineKeyboardButton("🗑 Delete a word", callback_data="MYWORDS|DELETE")])
    kb.append([InlineKeyboardButton("🧹 Bulk delete", callback_data="MYWORDS|BULK")])
    kb.append([InlineKeyboardButton("✏️ Rename category", callback_data="MYWORDS|RENAME")])
    kb.append([InlineKeyboardButton("🔁 Review My Words", callback_data="MYWORDS|REVIEW")])
    return "\n".join(lines), InlineKeyboardMarkup(kb)


def _category_select_keyboard(categories: List[str], prefix: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(cat, callback_data=f"{prefix}{cat}")] for cat in categories]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="MYWORDS|BACK")])
    return InlineKeyboardMarkup(rows)


def _conjugation_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("Present", callback_data="ADDWORD|CONJ|Present"),
            InlineKeyboardButton("Imperfect", callback_data="ADDWORD|CONJ|Imperfect"),
        ],
        [
            InlineKeyboardButton("Past (Passato prossimo)", callback_data="ADDWORD|CONJ|Past"),
            InlineKeyboardButton("Future", callback_data="ADDWORD|CONJ|Future"),
        ],
        [
            InlineKeyboardButton("Conditional", callback_data="ADDWORD|CONJ|Conditional"),
            InlineKeyboardButton("Subjunctive", callback_data="ADDWORD|CONJ|Subjunctive"),
        ],
        [
            InlineKeyboardButton("Imperative", callback_data="ADDWORD|CONJ|Imperative"),
        ],
        [
            InlineKeyboardButton("Past Remote (Passato remoto)", callback_data="ADDWORD|CONJ|Past Remote"),
            InlineKeyboardButton("Pluperfect (Trapassato prossimo)", callback_data="ADDWORD|CONJ|Pluperfect"),
        ],
        [
            InlineKeyboardButton("Past Anterior (Trapassato remoto)", callback_data="ADDWORD|CONJ|Past Anterior"),
            InlineKeyboardButton("Future Perfect (Futuro anteriore)", callback_data="ADDWORD|CONJ|Future Perfect"),
        ],
        [
            InlineKeyboardButton("Conditional Past", callback_data="ADDWORD|CONJ|Conditional Past"),
            InlineKeyboardButton("Subjunctive Imperfect", callback_data="ADDWORD|CONJ|Subjunctive Imperfect"),
        ],
        [
            InlineKeyboardButton("Subjunctive Pluperfect", callback_data="ADDWORD|CONJ|Subjunctive Pluperfect"),
            InlineKeyboardButton("Gerund", callback_data="ADDWORD|CONJ|Gerund"),
        ],
        [
            InlineKeyboardButton("Participle", callback_data="ADDWORD|CONJ|Participle"),
            InlineKeyboardButton("Infinitive", callback_data="ADDWORD|CONJ|Infinitive"),
        ],
        [
            InlineKeyboardButton("⬅️ Back to card", callback_data="ADDWORD|BACK"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


async def _send_tts(message, text: str):
    audio_path = await tts_it(text)
    suffix = audio_path.suffix.lower()
    with open(audio_path, "rb") as f:
        if suffix == ".ogg":
            await message.reply_voice(voice=InputFile(f, filename=f"{text}.ogg"))
        else:
            await message.reply_audio(audio=InputFile(f, filename=f"{text}{suffix}"), title=text)


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_chat_sender(update)
    clear_session(update.effective_user.id)
    set_session(update.effective_user.id, mode="addword", item_id=None, stage="await_input", meta={})
    await msg.reply_text("Send 1 word or a comma-separated list.")


async def mywords_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = get_chat_sender(update)
    profile = get_user_profile(user.id)
    if not profile:
        await msg.reply_text("Use /start first.")
        return
    target, ui, helper = profile
    pack_id = ensure_my_words_pack(user.id, target)
    categories = list_my_words_categories(pack_id)
    if not categories:
        await msg.reply_text("No saved words yet. Use /add to save your first word.")
        return
    text, kb = _mywords_menu(pack_id)
    await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def on_mywords_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    user = query.from_user
    parts = (query.data or "").split("|", 2)
    if len(parts) < 2:
        return
    action = parts[1]
    profile = get_user_profile(user.id)
    if not profile:
        await query.edit_message_text("Use /start first.")
        return
    target, ui, helper = profile
    pack_id = ensure_my_words_pack(user.id, target)

    if action == "BACK":
        text, kb = _mywords_menu(pack_id)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if action == "REVIEW":
        from bot.handlers.review import review_pack
        await query.edit_message_text("🔁 Starting My Words review…")
        await review_pack(update, context, pack_id)
        return

    if action == "DELETE":
        set_session(user.id, mode="addword", item_id=None, stage="await_delete", meta={})
        await query.message.reply_text("Send the word or phrase to delete.")
        return

    if action == "BULK":
        set_session(user.id, mode="addword", item_id=None, stage="await_bulk_delete", meta={})
        await query.message.reply_text("Send a comma-separated list of words/phrases to delete.")
        return

    if action == "SEARCH":
        set_session(user.id, mode="addword", item_id=None, stage="await_search", meta={})
        await query.message.reply_text("Send a word to search.")
        return

    if action == "CATS":
        categories = list_my_words_categories(pack_id)
        if not categories:
            await query.edit_message_text("No categories yet.")
            return
        lines = ["📂 <b>Categories</b>"]
        kb = []
        for cat, count in categories:
            lines.append(f"• {h(cat)} ({count})")
            kb.append([InlineKeyboardButton(f"{cat} ({count})", callback_data=f"MYWORDS|CAT|{cat}")])
        kb.append([InlineKeyboardButton("⬅️ Back", callback_data="MYWORDS|BACK")])
        await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
        return

    if action == "ALL":
        terms, total = list_my_words_all(pack_id, limit=50)
        if not terms:
            await query.edit_message_text("No saved words yet.")
            return
        lines = [f"🗂 <b>All My Words</b> ({total})"]
        for t in terms:
            lines.append(f"• {h(t)}")
        if total > len(terms):
            lines.append(f"…and {total - len(terms)} more")
        await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="MYWORDS|BACK")]
        ]))
        return

    if action == "RENAME":
        categories = list_my_words_categories(pack_id)
        if not categories:
            await query.edit_message_text("No categories to rename yet.")
            return
        cat_names = [c for c, _ in categories]
        kb = _category_select_keyboard(cat_names, "MYWORDS|RENFROM|")
        await query.edit_message_text("Pick a category to rename:", reply_markup=kb)
        return

    if action == "RENFROM" and len(parts) == 3:
        old_cat = parts[2]
        set_session(user.id, mode="addword", item_id=None, stage="rename_category", meta={"rename_from": old_cat})
        kb = _category_select_keyboard(CATEGORIES, "MYWORDS|RENTO|")
        await query.edit_message_text(f"Rename <b>{h(old_cat)}</b> to:", parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if action == "RENTO" and len(parts) == 3:
        session = get_session(user.id)
        old_cat = (session[3] or {}).get("rename_from") if session else None
        new_cat = parts[2]
        if not old_cat:
            await query.edit_message_text("Rename session expired. Try again.")
            return
        changed = rename_my_words_category(pack_id, old_cat, new_cat)
        clear_session(user.id)
        await query.edit_message_text(f"Renamed {changed} items to <b>{h(new_cat)}</b>.", parse_mode=ParseMode.HTML)
        return

    if action == "CAT" and len(parts) == 3:
        cat = parts[2]
        terms = list_my_words_in_category(pack_id, cat)
        if not terms:
            await query.edit_message_text("No words in this category yet.")
            return
        lines = [f"🗂 <b>{h(cat)}</b>"]
        for t in terms[:30]:
            lines.append(f"• {h(t)}")
        await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return


async def on_addword_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = get_chat_sender(update)
    text = (update.message.text or "").strip()

    session = get_session(user.id)
    if not session:
        return
    mode, item_id, stage, meta = session
    if mode != "addword":
        return

    if stage == "await_input":
        terms = _parse_terms(text, limit=100)
        if not terms:
            await msg.reply_text("Please send at least one word.")
            return
        meta = {"queue": terms, "index": 0}
        set_session(user.id, mode="addword", item_id=None, stage="show_card", meta=meta)
        await _process_current_word(update, context, meta)
        return

    if stage == "await_delete":
        profile = get_user_profile(user.id)
        if not profile:
            await msg.reply_text("Use /start first.")
            return
        target, ui, helper = profile
        pack_id = ensure_my_words_pack(user.id, target)
        term = text.strip()
        if not term:
            await msg.reply_text("Send the exact word or phrase to delete.")
            return
        from bot.db import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT item_id FROM pack_items WHERE pack_id = ? AND term = ?", (pack_id, term))
        row = cur.fetchone()
        if not row:
            conn.close()
            await msg.reply_text("Not found in your My Words.")
            return
        item_id = row[0]
        cur.execute("DELETE FROM pack_items WHERE item_id = ?", (item_id,))
        cur.execute("DELETE FROM card_contexts WHERE item_id = ?", (item_id,))
        cur.execute("DELETE FROM reviews WHERE item_id = ? AND user_id = ?", (item_id, user.id))
        conn.commit()
        conn.close()
        clear_session(user.id)
        await msg.reply_text(
            f"Deleted: {term}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="MYWORDS|BACK")]]),
        )
        return

    if stage == "await_bulk_delete":
        profile = get_user_profile(user.id)
        if not profile:
            await msg.reply_text("Use /start first.")
            return
        target, ui, helper = profile
        pack_id = ensure_my_words_pack(user.id, target)
        terms = _parse_terms(text)
        if not terms:
            await msg.reply_text("Send a comma-separated list of words to delete.")
            return
        from bot.db import get_connection
        conn = get_connection()
        cur = conn.cursor()
        placeholders = ",".join("?" for _ in terms)
        cur.execute(
            f"SELECT item_id, term FROM pack_items WHERE pack_id = ? AND term IN ({placeholders})",
            (pack_id, *terms),
        )
        rows = cur.fetchall()
        found = {r[1]: r[0] for r in rows}
        missing = [t for t in terms if t not in found]
        item_ids = list(found.values())
        if item_ids:
            id_placeholders = ",".join("?" for _ in item_ids)
            cur.execute(f"DELETE FROM pack_items WHERE item_id IN ({id_placeholders})", item_ids)
            cur.execute(f"DELETE FROM card_contexts WHERE item_id IN ({id_placeholders})", item_ids)
            cur.execute(
                f"DELETE FROM reviews WHERE user_id = ? AND item_id IN ({id_placeholders})",
                (user.id, *item_ids),
            )
        conn.commit()
        conn.close()
        clear_session(user.id)
        lines = [f"Deleted: {len(item_ids)}"]
        if missing:
            lines.append("Not found: " + ", ".join(missing[:10]))
        await msg.reply_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="MYWORDS|BACK")]]),
        )
        return

    if stage == "await_search":
        profile = get_user_profile(user.id)
        if not profile:
            await msg.reply_text("Use /start first.")
            return
        target, ui, helper = profile
        pack_id = ensure_my_words_pack(user.id, target)
        q = text.strip()
        if not q:
            await msg.reply_text("Send a word to search.")
            return
        terms = list_my_words_search(pack_id, q)
        if not terms:
            await msg.reply_text(
                "No matches.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="MYWORDS|BACK")]]),
            )
            return
        lines = [f"🔎 Results for <b>{h(q)}</b>:"]
        for t in terms[:30]:
            lines.append(f"• {h(t)}")
        await msg.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="MYWORDS|BACK")]
        ]))
        return

    if stage == "await_sentence":
        card = (meta or {}).get("card") or {}
        term = card.get("term") or ""
        ok, _ = validate_sentence(text, term, min_hits=1)
        if not ok:
            await msg.reply_text(f"⚠️ Your sentence must include <b>{h(term)}</b>.", parse_mode=ParseMode.HTML)
            return
        level_from = get_user_level(user.id)
        level_to = _next_level(level_from)
        upgrade = await generate_sentence_upgrade(
            term=term,
            user_sentence=text,
            level_from=level_from,
            level_to=level_to,
        )
        out = [
            f"✅ <b>{h(term)}</b>",
            "",
            f"Your sentence:\n“{h(text)}”",
        ]
        if upgrade.get("ok"):
            if upgrade.get("better"):
                out.append(f"\nBetter ({level_from}):\n{h(upgrade['better'])}")
            if upgrade.get("level_up"):
                out.append(f"\nLevel‑up ({level_to}):\n{h(upgrade['level_up'])}")
            if upgrade.get("native_sentence"):
                out.append(f"\nNative:\n{h(upgrade['native_sentence'])}")
            if upgrade.get("tip"):
                out.append(f"\nTip:\n{h(upgrade['tip'])}")
        else:
            fb = await generate_learn_feedback(
                target_language="it",
                term=term,
                chunk=term,
                translation_en=card.get("meaning_en"),
                user_sentence=text,
                lexicon=get_or_fetch_lexicon_it(term),
            )
            if fb.get("correction"):
                out.append(f"\nFix:\n{h(fb['correction'])}")
            elif fb.get("rewrite"):
                out.append(f"\nBetter:\n{h(fb['rewrite'])}")
            examples = fb.get("examples") or []
            if examples and examples[0]:
                out.append(f"\nNative:\n{h(examples[0])}")
            if fb.get("notes"):
                out.append(f"\nTip:\n{h(fb['notes'])}")
        await msg.reply_text(
            "\n".join(out),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to card", callback_data="ADDWORD|BACK")]]),
        )
        return

    if stage == "await_phrase":
        card = (meta or {}).get("card") or {}
        expected = (meta or {}).get("expected_phrase") or card.get("term") or ""
        ok, _ = validate_sentence(text, expected, min_hits=1)
        if not ok:
            await msg.reply_text("⚠️ Try again. Use the key phrase.")
            return
        await msg.reply_text("✅ Good.", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back to card", callback_data="ADDWORD|BACK")]
        ]))
        return


async def _process_current_word(update: Update, context: ContextTypes.DEFAULT_TYPE, meta: dict):
    user = update.effective_user
    msg = get_chat_sender(update)
    profile = get_user_profile(user.id)
    if not profile:
        await msg.reply_text("Use /start first.")
        return
    target, ui, helper = profile

    queue = meta.get("queue") or []
    idx = int(meta.get("index") or 0)
    if idx >= len(queue):
        clear_session(user.id)
        await msg.reply_text("All done.")
        return

    term = queue[idx]
    focus = "phrase" if _is_phrase(term) else "word"
    skip_validation = bool(meta.get("skip_validation")) and meta.get("skip_term") == term
    if not skip_validation:
        v = validate_it_term(term)
        if not v.get("ok") and focus == "word":
            sug = v.get("suggestion")
            if sug:
                meta["suggestion"] = sug
                meta["skip_term"] = term
                set_session(user.id, mode="addword", item_id=None, stage="show_card", meta=meta)
                await msg.reply_text(
                    f"Did you mean <b>{h(sug)}</b>?",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🟢 Use mine", callback_data="ADDWORD|USE_ORIG")],
                        [InlineKeyboardButton("✅ Use suggestion", callback_data="ADDWORD|USE_SUG")],
                        [InlineKeyboardButton("⏭ Skip", callback_data="ADDWORD|NEXT")],
                    ])
                )
                return
            await msg.reply_text("Word not found. Skipping.")
            meta["index"] = int(meta.get("index") or 0) + 1
            await _process_current_word(update, context, meta)
            return
    else:
        meta["skip_validation"] = False

    card = await generate_word_card(term=term, focus=focus, helper_language=helper or "fa")
    if not card or not card.get("ok"):
        card = {
            "term": term,
            "focus": focus,
            "meaning_en": "(meaning unavailable)",
            "meaning_helper": "",
            "examples": [],
            "senses": [],
        }

    meta["helper_lang"] = helper
    meta["card"] = card
    set_session(user.id, mode="addword", item_id=None, stage="show_card", meta=meta)

    text = _phrase_card_text(card, helper) if focus == "phrase" else _word_card_text(card, helper)
    has_next = idx + 1 < len(queue)
    await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=_card_keyboard(has_next, focus == "phrase"))


async def _save_current_word(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    profile = get_user_profile(user.id)
    if not profile:
        return 0
    target, ui, helper = profile
    session = get_session(user.id)
    if not session:
        return 0
    mode, item_id, stage, meta = session
    card = (meta or {}).get("card") or {}
    term = card.get("term") or ""
    focus = card.get("focus") or ("phrase" if _is_phrase(term) else "word")

    pack_id = ensure_my_words_pack(user.id, target)
    source_uid = f"user_{user.id}_{focus}_{_slugify(term)}"

    note_json = None
    if card:
        note_json = json.dumps(card, ensure_ascii=False)

    item_id = upsert_my_word_item(
        pack_id=pack_id,
        focus=focus,
        term=term,
        meaning_en=card.get("meaning_en"),
        meaning_helper=card.get("meaning_helper"),
        note_json=note_json,
        category=None,
        tags_json=None,
        cultural_note=card.get("cultural_note"),
        trap=card.get("trap"),
        native_sauce=card.get("native_sauce"),
        register=card.get("register"),
        risk=card.get("risk"),
        source_uid=source_uid,
    )

    # contexts
    for ex in (card.get("examples") or []):
        it = ex.get("it") or ""
        if it:
            upsert_card_context(item_id, it, lang="it")

    ensure_review_row(user.id, item_id)
    meta["saved_item_id"] = item_id
    set_session(user.id, mode="addword", item_id=item_id, stage="show_card", meta=meta)
    return item_id


async def _set_category(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str):
    user = update.effective_user
    session = get_session(user.id)
    if not session:
        return
    mode, item_id, stage, meta = session
    if mode != "addword":
        return
    item_id = int(meta.get("saved_item_id") or 0)
    if not item_id:
        await _save_current_word(update, context)
        item_id = int(meta.get("saved_item_id") or 0)
    if not item_id:
        return

    # update category directly
    from bot.db import get_connection
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE pack_items SET category = ? WHERE item_id = ?", (category, item_id))
    conn.commit()
    conn.close()

    await get_chat_sender(update).reply_text(f"Saved under category: {category}")


async def on_addword_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    user = query.from_user
    session = get_session(user.id)
    if not session:
        await query.edit_message_text("Session expired. Use /add again.")
        return
    mode, item_id, stage, meta = session
    if mode != "addword":
        return

    parts = (query.data or "").split("|")
    action = parts[1] if len(parts) > 1 else ""

    if action == "USE_SUG":
        sug = meta.get("suggestion")
        if sug:
            queue = meta.get("queue") or []
            idx = int(meta.get("index") or 0)
            if idx < len(queue):
                queue[idx] = sug
                meta["queue"] = queue
            await _process_current_word(update, context, meta)
            return
    if action == "USE_ORIG":
        meta["skip_validation"] = True
        await _process_current_word(update, context, meta)
        return

    if action == "SAVE":
        await _save_current_word(update, context)
        card = (meta.get("card") or {})
        suggestions = _normalize_categories(card.get("suggested_categories"), card.get("term"))
        await query.message.reply_text(
            "Suggested categories:",
            reply_markup=_category_keyboard(suggestions)
        )
        return

    if action == "CATS":
        await _save_current_word(update, context)
        card = (meta.get("card") or {})
        suggestions = _normalize_categories(card.get("suggested_categories"), card.get("term"))
        await query.message.reply_text(
            "Suggested categories:",
            reply_markup=_category_keyboard(suggestions)
        )
        return

    if action == "CAT":
        # handled via callback format ADDWORD|CAT|...
        return

    if action == "GRAMMAR":
        card = (meta or {}).get("card") or {}
        note = card.get("grammar") or "No grammar notes."
        await query.message.reply_text(f"🧠 Grammar: {h(note)}", parse_mode=ParseMode.HTML)
        return

    if action == "CULTURE":
        card = (meta or {}).get("card") or {}
        note = card.get("cultural_note") or "No cultural note."
        await query.message.reply_text(f"🌶 {h(note)}", parse_mode=ParseMode.HTML)
        return

    if action == "CONJ":
        card = (meta or {}).get("card") or {}
        term = card.get("term") or ""
        if len(parts) == 2:
            has_conj = bool(card.get("conjugation"))
            looks_like_verb = any(term.endswith(suf) for suf in ("are", "ere", "ire"))
            if not (has_conj or looks_like_verb):
                await query.message.reply_text(
                    "No conjugation available.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to card", callback_data="ADDWORD|BACK")]]),
                )
                return
            await query.message.reply_text(
                "Choose a tense:",
                reply_markup=_conjugation_keyboard(),
            )
            return
        tense = parts[2] if len(parts) > 2 else "Present"
        if tense == "Present" and card.get("conjugation"):
            text = f"🧾 {h(tense)}\n{h(card.get('conjugation'))}"
        else:
            conj = await generate_conjugation(term=term, tense=tense)
            if conj.get("ok") and conj.get("conjugation"):
                text = f"🧾 {h(tense)}\n{h(conj['conjugation'])}"
            else:
                text = f"🧾 {h(tense)}\nConjugation unavailable."
        await query.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to conjugations", callback_data="ADDWORD|CONJ")]]),
        )
        return

    if action == "PRON":
        card = (meta or {}).get("card") or {}
        term = card.get("term") or ""
        try:
            await _send_tts(query.message, term)
        except Exception as e:
            await query.message.reply_text(
                f"Pronunciation unavailable ({type(e).__name__}).",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 Retry", callback_data="ADDWORD|PRON")],
                    [InlineKeyboardButton("🩺 TTS Check", callback_data="TTS|CHECK")],
                ]),
            )
        return

    if action == "LEARN":
        card = (meta or {}).get("card") or {}
        focus = card.get("focus") or "word"
        if focus == "phrase":
            scenario = card.get("scenario")
            if not scenario:
                scenario = await generate_phrase_scenario(
                    term=card.get("term"),
                    meaning_en=card.get("meaning_en"),
                    helper_language=(meta or {}).get("helper_lang") or "fa",
                    level=get_user_level(user.id),
                )
            meta["expected_phrase"] = card.get("term")
            meta["scenario"] = scenario
            set_session(user.id, mode="addword", item_id=None, stage="await_phrase", meta=meta)
            text = (
                "🎭 Mini Scene\n"
                f"{h((scenario or {}).get('setting') or 'Real life')}\n\n"
                f"🧑‍💼 NPC: {h((scenario or {}).get('npc_line') or 'Mi dica.')}\n\n"
                f"Task: {h((scenario or {}).get('task') or 'Respond.')}")
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💡 Help", callback_data="ADDWORD|HELP")]
            ]))
            return
        # word learn
        set_session(user.id, mode="addword", item_id=None, stage="await_sentence", meta=meta)
        await query.message.reply_text(
            f"Use the word: <b>{h(card.get('term'))}</b>\nWrite a short, real sentence (up to 12 words).",
            parse_mode=ParseMode.HTML
        )
        return

    if action == "HELP":
        scenario = (meta or {}).get("scenario") or {}
        card = (meta or {}).get("card") or {}
        expected = (meta or {}).get("expected_phrase") or card.get("term") or ""
        hint = scenario.get("hint") or expected
        meaning_en = scenario.get("meaning_en") or card.get("meaning_en") or ""
        meaning_helper = scenario.get("meaning_helper") or card.get("meaning_helper") or ""
        grammar = card.get("grammar") or ""

        lines = [f"💡 <b>Hint</b>\n{h(hint)}"]
        if meaning_en or meaning_helper:
            lines.append("")
            lines.append("Meaning:")
            if meaning_en:
                lines.append(f"EN: {h(meaning_en)}")
            if meaning_helper:
                lines.append(f"FA: {h(meaning_helper)}")
        if grammar:
            lines.append("")
            lines.append(f"Grammar:\n{h(grammar)}")
        await query.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return

    if action == "BACK":
        card = (meta or {}).get("card") or {}
        helper_lang = (meta or {}).get("helper_lang")
        focus = card.get("focus") or "word"
        text = _phrase_card_text(card, helper_lang) if focus == "phrase" else _word_card_text(card, helper_lang)
        has_next = (meta.get("index") or 0) + 1 < len(meta.get("queue") or [])
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=_card_keyboard(has_next, focus == "phrase"))
        return

    if action == "NEXT":
        queue = meta.get("queue") or []
        idx = int(meta.get("index") or 0) + 1
        meta["index"] = idx
        if idx >= len(queue):
            clear_session(user.id)
            await query.message.reply_text("All done.")
            return
        await _process_current_word(update, context, meta)
        return

    if action == "CANCEL":
        clear_session(user.id)
        await query.message.reply_text("Cancelled.")
        return


async def on_addword_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    parts = (query.data or "").split("|", 2)
    if len(parts) < 3:
        return
    cat = parts[2]
    if cat == "SKIP":
        await query.message.reply_text("Category skipped.")
        return
    await _set_category(update, context, cat)
