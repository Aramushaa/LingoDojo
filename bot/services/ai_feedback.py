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


def _extract_json(text: str) -> Optional[dict]:
    text = (text or "").strip()
    if not text:
        return None

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    chunk = text[start:end+1]
    try:
        return json.loads(chunk)
    except Exception:
        return None


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
IMPORTANT RULES:
- Do NOT change the grammatical person/subject (io/tu/Lei/lui/lei/noi/voi/loro) unless the user sentence is clearly impossible.
- "correction" is ONLY for true grammar/spelling errors. If the sentence is acceptable, set correction = null.
- If you want to suggest a more polite version (e.g., "vorrei"), put it in "rewrite" and explain it's optional in notes.
- Do NOT assume we are practicing a specific form like "vorrei" unless the scenario explicitly says so.


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

async def generate_reverse_context_quiz(
    *,
    term: str,
    translation_en: Optional[str],
    lexicon: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Returns:
    {
      "ok": bool,
      "context_it": str,
      "meaning_en": str,
      "options_en": [str, str, str],
      "correct_index": 0|1|2,
      "clue": str
    }
    """
    # If AI not enabled, return a simple fallback quiz
    if AI_PROVIDER != "gemini" or not GEMINI_API_KEY:
        meaning = translation_en or "(meaning not available)"
        return {
            "ok": False,
            "context_it": f"Uso comune: {term}.",
            "meaning_en": meaning,
            "options_en": [meaning, "Something else", "Unrelated meaning"],
            "correct_index": 0,
            "clue": "Fallback (AI off).",
        }

    try:
        import google.genai as genai  # type: ignore

        client = genai.Client(api_key=GEMINI_API_KEY)
        model = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip()

        lex_str = json.dumps(lexicon or {}, ensure_ascii=False)

        prompt = f"""
Create a reverse-context meaning quiz for an Italian beginner.

WORD: "{term}"
Optional English hint (may be empty): "{translation_en or ""}"

GROUNDING (may be partial):
{lex_str}

Rules:
- Output MUST be valid JSON only.
- Make ONE short Italian context sentence that strongly implies the meaning.
- Provide 3 English options (A,B,C) with ONLY ONE correct.
- If hint is present, the correct option must align with it.
- Keep it beginner-friendly.

Return JSON:
{{
  "context_it": "...",
  "meaning_en": "...",
  "options_en": ["...","...","..."],
  "correct_index": 0,
  "clue": "short explanation of the clue"
}}
""".strip()

        resp = client.models.generate_content(model=model, contents=prompt)
        data = _extract_json((resp.text or "").strip())
        if not data:
            return {
                "ok": False,
                "context_it": f"Uso comune: {term}.",
                "meaning_en": translation_en or "(meaning not available)",
                "options_en": [translation_en or "Meaning", "Other", "Other"],
                "correct_index": 0,
                "clue": "AI returned invalid JSON.",
            }

        options = data.get("options_en") or []
        if not isinstance(options, list) or len(options) != 3:
            options = [translation_en or "Meaning", "Other", "Other"]

        idx = data.get("correct_index")
        if idx not in [0, 1, 2]:
            idx = 0

        return {
            "ok": True,
            "context_it": str(data.get("context_it") or "").strip(),
            "meaning_en": str(data.get("meaning_en") or (translation_en or "")).strip(),
            "options_en": [str(x).strip() for x in options],
            "correct_index": idx,
            "clue": str(data.get("clue") or "").strip(),
        }

    except Exception:
        # Never crash UX
        meaning = translation_en or "(meaning not available)"
        return {
            "ok": False,
            "context_it": f"Uso comune: {term}.",
            "meaning_en": meaning,
            "options_en": [meaning, "Something else", "Unrelated meaning"],
            "correct_index": 0,
            "clue": "AI error; fallback quiz.",
        }
