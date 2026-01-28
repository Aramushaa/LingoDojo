# bot/services/ai_feedback.py
from __future__ import annotations

import os
from typing import Dict, Any, Optional

# MVP: pluggable provider
AI_PROVIDER = os.getenv("AI_PROVIDER", "none").lower().strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()


def _fallback_feedback(user_sentence: str) -> Dict[str, Any]:
    # Always available, never crashes
    return {
        "ok": False,
        "correction": None,
        "notes": "AI is not configured yet. (Set AI_PROVIDER + API key to enable.)",
        "examples": [
            "Oggi vorrei prendere un caffè.",
            "Prendo un caffè al bar prima di andare al lavoro."
        ],
        "rewrite": None,
        "provider": "fallback",
    }


async def generate_learn_feedback(
    *,
    target_language: str,
    term: str,
    chunk: str,
    translation_en: Optional[str],
    user_sentence: str,
    dict_validation: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Returns a dict:
      {
        ok: bool,
        correction: str|None,
        rewrite: str|None,
        notes: str,
        examples: [str, ...],
        provider: str
      }

    IMPORTANT: Must never raise exceptions to callers.
    """
    # If AI not enabled, return fallback
    if AI_PROVIDER == "none" or not AI_PROVIDER:
        return _fallback_feedback(user_sentence)

    # ---- GEMINI (placeholder) ----
    # We keep this as a stub so your architecture is ready.
    # Later we will add actual Gemini SDK calls here.
    if AI_PROVIDER == "gemini":
        if not GEMINI_API_KEY:
            return _fallback_feedback(user_sentence)

        # TODO: implement real Gemini call (Phase 2.2)
        # For now we return fallback so nothing breaks.
        return _fallback_feedback(user_sentence)

    # Unknown provider → fallback
    return _fallback_feedback(user_sentence)
