from __future__ import annotations
from typing import Any, Dict, List, Tuple


def _require(cond: bool, msg: str, errors: List[str]):
    if not cond:
        errors.append(msg)


def validate_pack_v2(pack: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    _require(isinstance(pack.get("pack_id"), str) and pack["pack_id"].strip(), "pack_id missing", errors)
    _require(pack.get("target_language") in ("it", "en", "fr", "de", "es") or isinstance(pack.get("target_language"), str),
             "target_language missing/invalid", errors)
    _require(isinstance(pack.get("level"), str) and pack["level"].strip(), "level missing", errors)
    _require(isinstance(pack.get("title"), str) and pack["title"].strip(), "title missing", errors)
    _require(isinstance(pack.get("cards"), list) and len(pack["cards"]) > 0, "cards missing/empty", errors)

    seen_card_ids = set()

    for i, card in enumerate(pack.get("cards", [])):
        prefix = f"cards[{i}]"
        cid = card.get("card_id")
        _require(isinstance(cid, str) and cid.strip(), f"{prefix}.card_id missing", errors)
        if isinstance(cid, str):
            _require(cid not in seen_card_ids, f"{prefix}.card_id duplicate: {cid}", errors)
            seen_card_ids.add(cid)

        focus = card.get("focus")
        _require(focus in ("word", "phrase"), f"{prefix}.focus must be 'word' or 'phrase'", errors)

        if focus == "word":
            _require(isinstance(card.get("lemma"), str) and card["lemma"].strip(), f"{prefix}.lemma required for word", errors)
        if focus == "phrase":
            _require(isinstance(card.get("phrase"), str) and card["phrase"].strip(), f"{prefix}.phrase required for phrase", errors)

        _require(isinstance(card.get("meaning_en"), str) and card["meaning_en"].strip(), f"{prefix}.meaning_en missing", errors)

        contexts = card.get("contexts_it")
        _require(isinstance(contexts, list) and len(contexts) >= 1, f"{prefix}.contexts_it must be a non-empty list", errors)

        meta = card.get("meta") or {}
        _require(isinstance(meta, dict), f"{prefix}.meta must be object", errors)
        _require(isinstance(meta.get("register", ""), str), f"{prefix}.meta.register missing", errors)
        _require(isinstance(meta.get("risk", ""), str), f"{prefix}.meta.risk missing", errors)

        drills = card.get("drills") or {}
        _require(isinstance(drills, dict), f"{prefix}.drills must be object", errors)
        _require(isinstance(drills.get("scenario_prompt", ""), str) and drills.get("scenario_prompt", "").strip(),
                 f"{prefix}.drills.scenario_prompt missing", errors)

    # scenes optional
    scenes = pack.get("scenes")
    if scenes is not None:
        _require(isinstance(scenes, list), "scenes must be list if provided", errors)

    return (len(errors) == 0), errors
