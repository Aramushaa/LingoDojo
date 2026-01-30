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
    lex_str = json.dumps(lexicon or {}, ensure_ascii=False)

    return f"""
You are a professional Italian language tutor.

The user is a BEGINNER.
Your role is to help them learn naturally, without overcorrecting.

LEARNING CONTEXT:
- Target word: "{term}"
- Optional related chunk (reference only): "{chunk}"
- English hint for the word: "{translation_en or ""}"
- User's sentence (free form, any person allowed):
"{user_sentence}"

DICTIONARY / LEXICON FACTS (ground truth, may be partial):
{lex_str}

CORE RULES (VERY IMPORTANT):
1) The user is practicing the WORD, not a specific tense or structure.
2) Do NOT change the grammatical person or subject
   (io / tu / lui / lei / Lei / noi / voi / loro)
   unless the sentence is grammatically impossible.
3) If the user's sentence is grammatically acceptable Italian,
   DO NOT correct it.
4) "correction" is ONLY for true grammar or spelling errors.
   If the sentence is acceptable, set correction = null.
5) Style improvements (politeness, register, naturalness)
   MUST go in "rewrite" and are OPTIONAL suggestions.
6) Never invent meanings or usages.
   If dictionary grounding is missing or uncertain, say so briefly in notes.

OUTPUT FORMAT:
- Output MUST be valid JSON ONLY.
- No markdown, no explanations outside JSON.
- Use EXACTLY these keys:

{{
  "correction": string | null,
  "rewrite": string | null,
  "notes": string,
  "examples": [string, string, string]
}}

FIELD GUIDELINES:
- correction:
  Minimal fix only (articles, prepositions, verb form, spelling).
- rewrite:
  A more natural or polite alternative with the SAME meaning
  (optional; may be null).
- notes:
  Max 2 short lines.
  Explain meaning, register, or a useful real-life tip.
- examples:
  Exactly 3 short, natural Italian examples
  that clearly reflect the SAME meaning of the word
  (neutral / spoken / polite if possible).

TEACHING STYLE:
- Respect correct answers.
- Do not turn this into a grammar lecture.
- Be supportive, clear, and practical.
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
        data = _extract_json(text)
        if not data:
            return _fallback_feedback(user_sentence, reason="AI returned invalid JSON")

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
    chunk: Optional[str],
    translation_en: Optional[str],
    lexicon: Optional[dict] = None,
    context_it: Optional[str] = None,   # ✅ NEW
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
        FIXED CONTEXT (if provided, USE IT as the context sentence):
        "{context_it or ""}"


        TARGET WORD (TERM): "{term}"
        Related chunk (reference only, DO NOT teach chunk meaning): "{chunk or ""}"
        English hint (may be empty or may describe the chunk): "{translation_en or ""}"

        GROUNDING FACTS (if present, treat as truth):
        {lex_str}

        NON-NEGOTIABLE RULES:
        - If FIXED CONTEXT is provided and non-empty, you MUST use it as "context_it" exactly.
        - The quiz is ONLY about the TERM meaning, not the chunk.
        - For "andare", meaning must be "to go" (NOT "to go home").
        - If the hint seems chunk-specific (e.g., 'to go home'), IGNORE it and still quiz the TERM.
        - Context sentence must clearly support the TERM meaning.
        - Provide exactly 3 English options and exactly one correct.

        Output MUST be valid JSON only with this schema:
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
        meaning_en = str(data.get("meaning_en") or (translation_en or "")).strip()

        # Guardrail: prevent chunk meaning leaking into term meaning
        if term.lower() == "andare" and "home" in meaning_en.lower():
            meaning_en = "to go"


        options = data.get("options_en") or []
        if not isinstance(options, list) or len(options) != 3:
            options = [translation_en or "Meaning", "Other", "Other"]

        idx = data.get("correct_index")
        if idx not in [0, 1, 2]:
            idx = 0

        return {
            "ok": True,
            "context_it": str(data.get("context_it") or "").strip(),
            "meaning_en": meaning_en,  # ✅ use the guarded one
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

async def generate_roleplay_feedback(
    *,
    target_language: str,
    user_sentence: str,
    setting: str = "",
    bot_role: str = ""
) -> dict:
    """
    Lightweight correction for roleplay.
    No forced vocabulary. Just correctness + naturalness.
    """
    prompt = f"""
You are a friendly native teacher.
Target language: {target_language}

Context:
- setting: {setting}
- bot role: {bot_role}

Student message:
{user_sentence}

Return JSON with:
- correction (string or "")
- rewrite (string or "")
- notes (string or "")
Keep it short. No essays.
"""
    # Use the same Gemini call style you already use inside generate_learn_feedback
    return _fallback_feedback(prompt)
