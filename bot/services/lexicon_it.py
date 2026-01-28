# bot/services/lexicon_it.py
from __future__ import annotations

from typing import Optional, Dict, Any
from bot.db import get_lexicon_cache_it, set_lexicon_cache_it
from bot.services.dictionary_it import validate_it_term  # your validator/suggester

# Later we can add a richer "fetch senses/IPA" function.
# For MVP: cache validation result + resolved title.
def get_or_fetch_lexicon_it(term: str) -> Dict[str, Any]:
    term = (term or "").strip()
    if not term:
        return {"ok": False, "reason": "empty"}

    cached = get_lexicon_cache_it(term)
    if cached:
        return cached

    # Fetch (best-effort)
    result = {"ok": True, "term": term, "source": "it.wiktionary"}
    try:
        v = validate_it_term(term)
        result["validation"] = v
    except Exception as e:
        result["ok"] = False
        result["source"] = "it.wiktionary"
        result["error"] = str(e)

    set_lexicon_cache_it(term, result)
    return result
