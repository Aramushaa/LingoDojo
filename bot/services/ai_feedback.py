# bot/services/ai_feedback.py
from __future__ import annotations
import google.genai as genai  # type: ignore

import os
import json
from typing import Dict, Any, Optional

AI_PROVIDER = os.getenv("AI_PROVIDER", "none").lower().strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip()



def _fallback_feedback(user_sentence: str, reason: str = "unknown") -> Dict[str, Any]:
    return {
        "ok": False,
        "correction": None,
        "notes": f"AI not available right now. ({reason})",
        "examples": [
            "Oggi vorrei prendere un caffè.",
            "Prendo un caffè al bar prima di andare al lavoro.",
        ],
        "rewrite": None,
        "provider": "fallback",
    }


def _build_prompt(
    *,
    term: str,
    chunk: str,
    translation_en: Optional[str],
    user_sentence: str,
    lexicon: Optional[dict],
) -> str:
    # We keep it short and strict: JSON output only.
    lex_str = json.dumps(lexicon or {}, ensure_ascii=False)

    return f"""
You are an Italian tutor. The user is a beginner. Be concise.

TASK:
- The user must practice this chunk: "{chunk}" (term: "{term}")
- English hint: "{translation_en or ""}"
- User sentence: "{user_sentence}"

GROUNDING (dictionary/lexicon cache, may be partial):
{lex_str}

RULES:
- Do NOT invent meanings.
- If grounding is missing/uncertain, say so briefly in notes.
- Output MUST be valid JSON only. No markdown.

Return JSON with exactly these keys:
{{
  "correction": string|null,
  "rewrite": string|null,
  "notes": string,
  "examples": [string, string, string]
}}

Guidance:
- correction: only fix the minimum (articles/prepositions/verb form), short.
- rewrite: a natural version of the user sentence (if user sentence is already good, can be null).
- notes: 1–2 lines max.
- examples: 3 short natural Italian examples using the chunk (neutral/formal/informal if possible).
""".strip()


async def generate_learn_feedback(
    *,
    target_language: str,
    term: str,
    chunk: str,
    translation_en: Optional[str],
    user_sentence: str,
    dict_validation: Optional[dict] = None,
    lexicon: Optional[dict] = None,
) -> Dict[str, Any]:
    # Always safe: never raise to caller
    try:
        if AI_PROVIDER != "gemini":
            return _fallback_feedback(user_sentence, reason=f"AI_PROVIDER={AI_PROVIDER!r}")

        if not GEMINI_API_KEY:
            return _fallback_feedback(user_sentence, reason="GEMINI_API_KEY missing/empty")


        from google import genai  # type: ignore

        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = _build_prompt(
            term=term,
            chunk=chunk,
            translation_en=translation_en,
            user_sentence=user_sentence,
            lexicon=lexicon or dict_validation,
        )

        resp = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )


        text = (resp.text or "").strip()
        data = json.loads(text)

        # Normalize
        correction = data.get("correction")
        rewrite = data.get("rewrite")
        notes = data.get("notes") or ""
        examples = data.get("examples") or []

        if not isinstance(examples, list):
            examples = []

        # Ensure 3 examples
        examples = [str(x) for x in examples][:3]
        while len(examples) < 3:
            examples.append("")

        return {
            "ok": True,
            "correction": correction,
            "rewrite": rewrite,
            "notes": notes,
            "examples": examples,
            "provider": "gemini",
        }

    except Exception as e:
        return _fallback_feedback(user_sentence, reason=f"exception: {type(e).__name__}: {e}")

def debug_list_models() -> str:
    try:
        import google.genai as genai  # type: ignore
        client = genai.Client(api_key=GEMINI_API_KEY)
        models = client.models.list()
        names = []
        for m in models:
            # m.name looks like "models/...."
            names.append(getattr(m, "name", str(m)))
        return "\n".join(names[:30])
    except Exception as e:
        return f"(could not list models: {type(e).__name__}: {e})"
