from __future__ import annotations

import json
from pathlib import Path
import unicodedata
import re
from typing import Any

from bot.db import has_completed_scenario, get_learned_terms_for_pack

SCENARIOS_DIR = Path("data/scenarios")


def _normalize(text: str) -> str:
    if not text:
        return ""
    text = text.replace("’", "'").strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9\s']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_scenarios() -> list[dict[str, Any]]:
    if not SCENARIOS_DIR.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in SCENARIOS_DIR.rglob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            out.append(data)
        except Exception:
            continue
    return out


def list_scenarios_by_pack_key(pack_key: str) -> list[dict[str, Any]]:
    return [s for s in load_scenarios() if s.get("pack_key") == pack_key]


def _pack_key_for_id(pack_id: str) -> str:
    pid = (pack_id or "").lower()
    if "airport" in pid and "a1" in pid:
        return "airport_a1"
    if "airport" in pid and "a2" in pid:
        return "airport_a2"
    if "airport" in pid and "b1" in pid:
        return "airport_b1"
    if "hotel" in pid and "a1" in pid:
        return "hotel_a1"
    if "hotel" in pid and "a2" in pid:
        return "hotel_a2"
    if "hotel" in pid and "b1" in pid:
        return "hotel_b1"
    return "generic"


def pick_scenario_for_pack(user_id: int, pack_id: str, chunk_terms: list[str]) -> dict | None:
    scenarios = load_scenarios()
    pack_key = _pack_key_for_id(pack_id)

    # normalize chunk terms for matching
    chunk_norm = {_normalize(t) for t in chunk_terms if t}

    # learned terms for this pack (for readiness)
    learned_terms = get_learned_terms_for_pack(user_id, pack_id)
    learned_norm = {_normalize(t) for t in learned_terms}

    # filter scenarios by pack_key
    candidates = [s for s in scenarios if s.get("pack_key") == pack_key]

    def is_ready(req: list[str], pool: set[str]) -> bool:
        req_norm = [_normalize(r) for r in req if r]
        return all(r in pool for r in req_norm)

    # first: scenarios fully covered by current chunk
    for s in candidates:
        sid = s.get("scenario_id")
        if sid and has_completed_scenario(user_id, sid):
            continue
        required = s.get("required_phrases") or []
        if required and is_ready(required, chunk_norm):
            return s

    # second: scenarios covered by learned items in the pack
    for s in candidates:
        sid = s.get("scenario_id")
        if sid and has_completed_scenario(user_id, sid):
            continue
        required = s.get("required_phrases") or []
        if required and is_ready(required, learned_norm):
            return s

    return None
