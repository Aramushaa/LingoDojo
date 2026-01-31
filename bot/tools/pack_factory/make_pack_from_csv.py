from __future__ import annotations
import csv
import json
import os
import re
import hashlib
from typing import Dict, Any, List

from bot.tools.pack_factory.schema_check import validate_pack_v2


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def stable_card_id(pack_id: str, focus: str, text: str) -> str:
    raw = f"{pack_id}|{focus}|{text.strip().lower()}"
    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    base = slugify(text)[:20] or "card"
    return f"{base}_{h}"


def split_pipe(s: str) -> List[str]:
    if not s:
        return []
    return [x.strip() for x in s.split("|") if x.strip()]


def split_tags(s: str) -> List[str]:
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


def row_to_card(pack_id: str, row: Dict[str, str]) -> Dict[str, Any]:
    focus = (row.get("focus") or "").strip().lower()
    lemma = (row.get("lemma") or "").strip()
    phrase = (row.get("phrase") or "").strip()
    phrase_hint = (row.get("phrase_hint") or "").strip()

    meaning_en = (row.get("meaning_en") or "").strip()
    contexts_it = split_pipe(row.get("contexts_it") or "")
    examples_it = split_pipe(row.get("examples_it") or "")

    register = (row.get("register") or "neutral").strip()
    risk = (row.get("risk") or "safe").strip()
    tags = split_tags(row.get("tags") or "")

    cultural_note = (row.get("cultural_note") or "").strip()
    trap = (row.get("trap") or "").strip()
    native_sauce = (row.get("native_sauce") or "").strip()

    scenario_prompt = (row.get("scenario_prompt") or "").strip()

    # Determine primary text for ID
    if focus == "word":
        primary = lemma
    else:
        primary = phrase

    card_id = stable_card_id(pack_id, focus, primary)

    card: Dict[str, Any] = {
        "source_uid": card_id,
        "card_id": card_id,
        "focus": focus,
        "meaning_en": meaning_en,
        "contexts_it": contexts_it,
        "meta": {
            "register": register,
            "risk": risk,
            "tags": tags,
        },
        "drills": {
            "scenario_prompt": scenario_prompt
        }
    }

    if focus == "word":
        card["lemma"] = lemma
        if phrase_hint:
            card["phrase_hint"] = phrase_hint
    else:
        card["phrase"] = phrase

    # Optional meta
    if cultural_note:
        card["meta"]["cultural_note"] = cultural_note
    if trap:
        card["meta"]["trap"] = trap
    if native_sauce:
        card["meta"]["native_sauce"] = native_sauce

    # Optional offline examples (future use)
    if examples_it:
        card["examples_it"] = examples_it[:3]

    return card


def make_pack_from_csv(
    *,
    csv_path: str,
    out_path: str,
    pack_id: str,
    target_language: str,
    level: str,
    title: str,
    description: str,
    pack_type: str = "mission"
):
    cards: List[Dict[str, Any]] = []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            focus = (row.get("focus") or "").strip().lower()
            if not focus:
                continue  # allow blank lines

            card = row_to_card(pack_id, row)
            cards.append(card)

    pack: Dict[str, Any] = {
        "pack_id": pack_id,
        "target_language": target_language,
        "level": level,
        "type": pack_type,
        "title": title,
        "description": description,
        "cards": cards,
        "scenes": []  # we’ll add scene CSV in v1.1 if you want
    }

    ok, errors = validate_pack_v2(pack)
    if not ok:
        raise SystemExit("Schema errors:\n" + "\n".join(f"- {e}" for e in errors))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=2)

    print(f"✅ Wrote: {out_path}  ({len(cards)} cards)")


if __name__ == "__main__":
    # Example usage (edit these values)
    make_pack_from_csv(
        csv_path="data/pack_sources/draft_it_a1_airport.csv",
        out_path="data/packs/it_a1_mission_airport_v2.json",
        pack_id="it_a1_mission_airport_v2",
        target_language="it",
        level="A1",
        title="✈️ Mission: Navigate an Italian Airport (A1)",
        description="Survive check-in, security, boarding, arrivals, and baggage with simple Italian.",
    )
