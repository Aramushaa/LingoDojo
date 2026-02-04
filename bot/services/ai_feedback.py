# bot/services/ai_feedback.py
from __future__ import annotations
import google.genai as genai  # type: ignore

import os
import json
import random
import hashlib
from typing import Dict, Any, Optional

from bot.db import ai_cache_get, ai_cache_set

AI_PROVIDER = os.getenv("AI_PROVIDER", "none").lower().strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_API_KEYS = [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()]
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip()
DEFAULT_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-3-flash",
    "gemini-2.5-flash-lite",
]

_gemini_key_idx = 0


def _next_gemini_key() -> str:
    """
    Round-robin across GEMINI_API_KEYS if provided, else fall back to GEMINI_API_KEY.
    """
    global _gemini_key_idx
    if GEMINI_API_KEYS:
        key = GEMINI_API_KEYS[_gemini_key_idx % len(GEMINI_API_KEYS)]
        _gemini_key_idx += 1
        return key
    return GEMINI_API_KEY


def _gemini_models() -> list[str]:
    """
    Model priority list. Use GEMINI_MODELS if set, else GEMINI_MODEL (if explicitly set),
    else default list.
    """
    env_list = [m.strip() for m in os.getenv("GEMINI_MODELS", "").split(",") if m.strip()]
    if env_list:
        return env_list
    if "GEMINI_MODEL" in os.environ and MODEL_NAME:
        return [MODEL_NAME]
    return DEFAULT_GEMINI_MODELS


def _is_quota_or_rate_error(err: Exception) -> bool:
    msg = str(err).lower()
    return any(
        token in msg
        for token in [
            "quota",
            "rate",
            "limit",
            "exceeded",
            "resource_exhausted",
            "429",
        ]
    )


def _num_keys() -> int:
    return len(GEMINI_API_KEYS) if GEMINI_API_KEYS else 1



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
    # strip common code fences
    if text.startswith("```"):
        text = text.strip("`").strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    chunk = text[start:end + 1]
    try:
        return json.loads(chunk)
    except Exception:
        return None


async def generate_sentence_upgrade(
    *,
    term: str,
    user_sentence: str,
    level_from: str = "A1",
    level_to: str = "A2",
) -> Dict[str, Any]:
    """
    Returns a better sentence + level-up version + native sentence.
    """
    raw_key = f"sentence_upgrade|{term}|{user_sentence}|{level_from}|{level_to}"
    cache_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    cached = ai_cache_get(cache_key)
    if cached:
        return cached

    if AI_PROVIDER != "gemini" or not (GEMINI_API_KEYS or GEMINI_API_KEY):
        out = {"ok": False}
        ai_cache_set(cache_key, out)
        return out

    prompt = f"""
You are an Italian tutor. Improve a learner sentence.

TERM: "{term}"
Learner sentence: "{user_sentence}"
Learner level: {level_from}
Target level: {level_to}

Return JSON only:
{{
  "ok": true,
  "better": "corrected or more natural same-level sentence",
  "level_up": "more natural version at next level",
  "native_sentence": "native-like sentence using the term",
  "tip": "one short tip for improvement"
}}
""".strip()

    last_err: Exception | None = None
    try:
        for model in _gemini_models():
            for _ in range(_num_keys()):
                try:
                    client = genai.Client(api_key=_next_gemini_key())
                    resp = client.models.generate_content(model=model, contents=prompt)
                    data = _extract_json((resp.text or "").strip())
                    if data:
                        data["ok"] = True
                        ai_cache_set(cache_key, data)
                        return data
                except Exception as e:
                    last_err = e
                    if _is_quota_or_rate_error(e):
                        continue
                    raise
    except Exception:
        pass

    out = {"ok": False, "error": str(last_err) if last_err else "ai_failed"}
    ai_cache_set(cache_key, out)
    return out


async def generate_word_card(
    *,
    term: str,
    focus: str,
    helper_language: str = "fa",
) -> Dict[str, Any]:
    """
    Returns a structured word/phrase card with meanings and examples.
    """
    term = (term or "").strip()
    focus = (focus or "word").strip().lower()
    raw_key = f"word_card|{focus}|{helper_language}|{term}"
    cache_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    cached = ai_cache_get(cache_key)
    if cached:
        return cached

    if AI_PROVIDER != "gemini" or not (GEMINI_API_KEYS or GEMINI_API_KEY):
        out = {"ok": False, "term": term, "focus": focus}
        ai_cache_set(cache_key, out)
        return out

    prompt = f"""
You are a professional Italian tutor.
Return a compact word/phrase card in JSON only.

TERM: "{term}"
FOCUS: "{focus}"  (word or phrase)
TARGET LANGUAGE: Italian
HELPER LANGUAGE: {helper_language}

Rules:
- Italian first, then English, then helper language.
- Keep output short and practical.
- If multiple meanings, return them as \"senses\" list.
- Provide exactly 3 examples. Each example: it + en + helper.
- Provide a short grammar note only if relevant.
- If focus=word and it's a verb, include short conjugation note (present tense only).
- Suggested categories: pick 2-4 from: Verbs, Travel, Food & Drink, Shopping, Daily Life, Work & Study, Emotions, Time & Dates, Politeness, General.
- Use \"safe\" risk unless it is clearly risky slang.

Output JSON schema:
{{
  "ok": true,
  "term": "...",
  "focus": "word|phrase",
  "meaning_en": "...",
  "meaning_helper": "...",
  "senses": [{{"meaning_en":"...", "meaning_helper":"...", "usage":"..."}}],
  "examples": [{{"it":"...", "en":"...", "helper":"..."}}],
  "grammar": "...",
  "conjugation": "...",
  "cultural_note": "...",
  "native_sauce": "...",
  "trap": "...",
  "register": "neutral|polite|slang",
  "risk": "safe|caution|avoid",
  "suggested_categories": ["...","..."]
}}
""".strip()

    last_err: Exception | None = None
    try:
        for model in _gemini_models():
            for _ in range(_num_keys()):
                try:
                    client = genai.Client(api_key=_next_gemini_key())
                    resp = client.models.generate_content(model=model, contents=prompt)
                    data = _extract_json((resp.text or "").strip())
                    if data:
                        data["ok"] = True
                        ai_cache_set(cache_key, data)
                        return data
                except Exception as e:
                    last_err = e
                    if _is_quota_or_rate_error(e):
                        continue
                    raise
    except Exception:
        pass

    out = {"ok": False, "term": term, "focus": focus, "error": str(last_err) if last_err else "ai_failed"}
    ai_cache_set(cache_key, out)
    return out


async def generate_conjugation(
    *,
    term: str,
    tense: str,
) -> Dict[str, Any]:
    """
    Returns a conjugation table for a given tense.
    """
    term = (term or "").strip()
    tense = (tense or "").strip()
    raw_key = f"conjugation|{term}|{tense}"
    cache_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    cached = ai_cache_get(cache_key)
    if cached:
        return cached

    if AI_PROVIDER != "gemini" or not (GEMINI_API_KEYS or GEMINI_API_KEY):
        out = {"ok": False, "term": term, "tense": tense}
        ai_cache_set(cache_key, out)
        return out

    prompt = f"""
You are an Italian tutor. Provide the conjugation of the verb.
Verb: "{term}"
Tense: "{tense}"

Return JSON only:
{{
  "ok": true,
  "tense": "{tense}",
  "conjugation": "io ...\\ntu ...\\nlui/lei ...\\nnoi ...\\nvoi ...\\nloro ..."
}}
""".strip()

    last_err: Exception | None = None
    try:
        for model in _gemini_models():
            for _ in range(_num_keys()):
                try:
                    client = genai.Client(api_key=_next_gemini_key())
                    resp = client.models.generate_content(model=model, contents=prompt)
                    data = _extract_json((resp.text or "").strip())
                    if data:
                        data["ok"] = True
                        ai_cache_set(cache_key, data)
                        return data
                except Exception as e:
                    last_err = e
                    if _is_quota_or_rate_error(e):
                        continue
                    raise
    except Exception:
        pass

    out = {"ok": False, "term": term, "tense": tense, "error": str(last_err) if last_err else "ai_failed"}
    ai_cache_set(cache_key, out)
    return out

async def generate_phrase_scenario(
    *,
    term: str,
    meaning_en: Optional[str] = None,
    helper_language: str = "fa",
    level: str = "A1",
) -> Dict[str, Any]:
    term = (term or "").strip()
    raw_key = f"phrase_scene|{helper_language}|{level}|{term}|{meaning_en or ''}"
    cache_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    cached = ai_cache_get(cache_key)
    if cached:
        return cached

    if AI_PROVIDER != "gemini" or not (GEMINI_API_KEYS or GEMINI_API_KEY):
        out = {"ok": False, "setting": "Real life", "npc_line": "Mi dica.", "task": "Respond."}
        ai_cache_set(cache_key, out)
        return out

    prompt = f"""
Create a very short mini-scene to practice this Italian phrase.
Tone: funny but real-life (not absurd).
Level: {level} (keep vocabulary and sentence structure at this level).

PHRASE: "{term}"
Meaning (EN): "{meaning_en or ''}"

Output JSON only:
{{
  "ok": true,
  "setting": "one short line",
  "npc_line": "one short line",
  "task": "what the user should say",
  "hint": "short hint",
  "meaning_en": "short meaning in English",
  "meaning_helper": "short meaning in helper language"
}}
""".strip()

    last_err: Exception | None = None
    try:
        for model in _gemini_models():
            for _ in range(_num_keys()):
                try:
                    client = genai.Client(api_key=_next_gemini_key())
                    resp = client.models.generate_content(model=model, contents=prompt)
                    data = _extract_json((resp.text or "").strip())
                    if data:
                        data["ok"] = True
                        ai_cache_set(cache_key, data)
                        return data
                except Exception as e:
                    last_err = e
                    if _is_quota_or_rate_error(e):
                        continue
                    raise
    except Exception:
        pass

    out = {"ok": False, "setting": "Real life", "npc_line": "Mi dica.", "task": "Respond.", "error": str(last_err) if last_err else "ai_failed"}
    ai_cache_set(cache_key, out)
    return out


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
  "why": [string, string],
  "grammar_notes": [
    {{"issue": string, "explain": string, "example": string}},
    {{"issue": string, "explain": string, "example": string}}
  ],
  "notes": string,
  "examples": [string, string, string]
}}

RULES FOR WHY + GRAMMAR:
- If correction is null, why MUST be [] and grammar_notes MUST be [].
- why: max 2 items, each ONE short sentence, beginner-friendly.
- grammar_notes: max 2 items, short, practical.

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
    # Cache key: same term + same sentence = reuse
    raw_key = f"learn_feedback|{target_language}|{term}|{user_sentence.strip()}"
    cache_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    cached = ai_cache_get(cache_key)
    if cached:
        cached["cached"] = True
        return cached

    # Always safe: never raise to caller
    try:
        if AI_PROVIDER != "gemini":
            return _fallback_feedback(user_sentence, reason=f"AI_PROVIDER={AI_PROVIDER!r}")

        if not (GEMINI_API_KEYS or GEMINI_API_KEY):
            return _fallback_feedback(user_sentence, reason="GEMINI_API_KEY(S) missing/empty")

        prompt = _build_prompt(
            term=term,
            chunk=chunk,
            translation_en=translation_en,
            user_sentence=user_sentence,
            lexicon=lexicon or dict_validation,
        )

        last_err: Exception | None = None
        for model in _gemini_models():
            for _ in range(_num_keys()):
                try:
                    client = genai.Client(api_key=_next_gemini_key())
                    resp = client.models.generate_content(
                        model=model,
                        contents=prompt,
                    )

                    text = (resp.text or "").strip()
                    data = _extract_json(text)
                    if not data:
                        return _fallback_feedback(user_sentence, reason="AI returned invalid JSON")

                    # Normalize
                    correction = data.get("correction")
                    rewrite = data.get("rewrite")
                    why = data.get("why") or []
                    if not isinstance(why, list):
                        why = []
                    why = [str(x).strip() for x in why if x][:2]

                    grammar_notes = data.get("grammar_notes") or []
                    if not isinstance(grammar_notes, list):
                        grammar_notes = []
                    grammar_notes = grammar_notes[:2]

                    notes = data.get("notes") or ""
                    examples = data.get("examples") or []
                    if not isinstance(examples, list):
                        examples = []

                    # Ensure 3 examples
                    examples = [str(x) for x in examples][:3]
                    while len(examples) < 3:
                        examples.append("")

                    result = {
                        "ok": True,
                        "correction": correction,
                        "rewrite": rewrite,
                        "why": why,
                        "grammar_notes": grammar_notes,
                        "notes": notes,
                        "examples": examples,
                        "provider": "gemini",
                    }
                    ai_cache_set(cache_key, result)
                    return result

                except Exception as e:
                    last_err = e
                    if _is_quota_or_rate_error(e):
                        continue
                    raise

        return _fallback_feedback(
            user_sentence,
            reason=f"quota/rate limit across keys/models: {type(last_err).__name__ if last_err else 'unknown'}",
        )

    except Exception as e:
        return _fallback_feedback(user_sentence, reason=f"exception: {type(e).__name__}: {e}")

def debug_list_models() -> str:
    try:
        import google.genai as genai  # type: ignore
        client = genai.Client(api_key=_next_gemini_key())
        models = client.models.list()
        names = []
        for m in models:
            # m.name looks like "models/...."
            names.append(getattr(m, "name", str(m)))
        return "\n".join(names[:30])
    except Exception as e:
        return f"(could not list models: {type(e).__name__}: {e})"

async def _generate_reverse_context_quiz_ai(
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
    if AI_PROVIDER != "gemini" or not (GEMINI_API_KEYS or GEMINI_API_KEY):
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
        last_err: Exception | None = None
        for model in _gemini_models():
            for _ in range(_num_keys()):
                try:
                    client = genai.Client(api_key=_next_gemini_key())
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
                except Exception as e:
                    last_err = e
                    if _is_quota_or_rate_error(e):
                        continue
                    raise

        meaning = translation_en or "(meaning not available)"
        return {
            "ok": False,
            "context_it": f"Uso comune: {term}.",
            "meaning_en": meaning,
            "options_en": [meaning, "Something else", "Unrelated meaning"],
            "correct_index": 0,
            "clue": "Quota/rate limit across keys/models.",
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

async def generate_reverse_context_quiz(
    *,
    term: str,
    chunk: Optional[str],
    translation_en: Optional[str],
    lexicon: Optional[dict] = None,
    context_it: Optional[str] = None,
    distractors_en: Optional[list[str]] = None
) -> Dict[str, Any]:
    """
    Offline reverse-context quiz (no AI calls).
    """
    meaning = (translation_en or "(meaning not available)").strip()

    # Build options: 1 correct + 2 distractors
    pool = [x.strip() for x in (distractors_en or []) if x and x.strip() and x.strip().lower() != meaning.lower()]

    # fallback distractors if pool too small
    fallback_pool = [
        "to eat", "to sleep", "to go", "to do", "to make",
        "a place", "a person", "a thing", "a problem", "an idea"
    ]
    for x in fallback_pool:
        if len(pool) >= 2:
            break
        if x.lower() != meaning.lower() and x not in pool:
            pool.append(x)

    pool = pool[:2]
    options = [meaning] + pool

    # shuffle
    random.shuffle(options)
    correct_index = options.index(meaning)

    ctx = (context_it or f"Uso comune: {term}.").strip()

    return {
        "ok": True,
        "context_it": ctx,
        "meaning_en": meaning,
        "options_en": options,
        "correct_index": correct_index,
        "clue": "Use the context to pick the closest meaning."
    }


async def generate_roleplay_feedback(
    *,
    target_language: str,
    user_sentence: str,
    setting: str = "",
    bot_role: str = "",
    expected_phrase: str | None = None,
    ui_language: str = "en",
    helper_language: str | None = None,
) -> dict:
    """
    Lightweight correction for roleplay.
    No forced vocabulary. Just correctness + naturalness.
    """
    try:
        if AI_PROVIDER != "gemini":
            return _fallback_feedback(user_sentence, reason=f"AI_PROVIDER={AI_PROVIDER!r}")

        if not (GEMINI_API_KEYS or GEMINI_API_KEY):
            return _fallback_feedback(user_sentence, reason="GEMINI_API_KEY(S) missing/empty")

        expected = (expected_phrase or "").strip()
        lang_primary = ui_language or "en"
        lang_helper = helper_language or ""
        prompt = f"""
You are a friendly native Italian tutor.
The user is a beginner.

ROLEPLAY CONTEXT:
- setting: {setting}
- bot role: {bot_role}

User message:
"{user_sentence}"

Expected phrase (if any):
{expected or "(none)"}

OUTPUT LANGUAGE:
- Write notes/tips/grammar in {lang_primary}.
- If {lang_helper or "no secondary language"} is provided, include a second line in that language in notes/tips/grammar (prefix each line with the language code, e.g. "EN:" / "FA:").

RULES:
- If an expected phrase is provided, set ok=false if the user did not use it (or a clear equivalent).
- Accept minor typos or extra words if the expected phrase is clearly present.
- If ok=false, notes should briefly say to use the expected phrase.
- Keep correction minimal.
- If acceptable, do not correct.
- rewrite is optional (more natural, same meaning).
- notes max 2 short lines.
- examples MUST be exactly 3 short sentences.
- Provide short "tips" and "grammar" only if helpful (max 2 bullets each).

Return JSON ONLY:
{{
  "ok": true/false,
  "correction": string | null,
  "rewrite": string | null,
  "notes": string,
  "examples": [string, string, string],
  "tips": [string, string],
  "grammar": [string, string]
}}
""".strip()
        last_err: Exception | None = None
        for model in _gemini_models():
            for _ in range(_num_keys()):
                try:
                    client = genai.Client(api_key=_next_gemini_key())
                    resp = client.models.generate_content(model=model, contents=prompt)
                    text = (resp.text or "").strip()

                    data = _extract_json(text)
                    if not data:
                        return _fallback_feedback(user_sentence, reason="AI returned invalid JSON")

                    ok = data.get("ok")
                    if ok is None:
                        ok = True
                    if isinstance(ok, str):
                        ok = ok.strip().lower() in ("true", "yes", "1")

                    examples = data.get("examples") or []
                    if not isinstance(examples, list):
                        examples = []
                    examples = [str(x) for x in examples][:3]
                    while len(examples) < 3:
                        examples.append("")

                    tips = data.get("tips") or []
                    if not isinstance(tips, list):
                        tips = []
                    tips = [str(x) for x in tips if x][:2]

                    grammar = data.get("grammar") or []
                    if not isinstance(grammar, list):
                        grammar = []
                    grammar = [str(x) for x in grammar if x][:2]

                    return {
                        "ok": bool(ok),
                        "correction": data.get("correction"),
                        "rewrite": data.get("rewrite"),
                        "notes": data.get("notes") or "",
                        "examples": examples,
                        "tips": tips,
                        "grammar": grammar,
                        "provider": "gemini",
                    }
                except Exception as e:
                    last_err = e
                    if _is_quota_or_rate_error(e):
                        continue
                    raise

        return _fallback_feedback(
            user_sentence,
            reason=f"quota/rate limit across keys/models: {type(last_err).__name__ if last_err else 'unknown'}",
        )

    except Exception as e:
        return _fallback_feedback(user_sentence, reason=f"exception: {type(e).__name__}: {e}")
