# bot/services/tts_edge.py
from __future__ import annotations

import os
import logging
from pathlib import Path
import hashlib
import edge_tts

CACHE_DIR = Path("bot_cache/tts")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

VOICE_IT = os.getenv("TTS_VOICE_IT", "it-IT-DiegoNeural")

# ✅ WAV PCM (most compatible with Telegram)
OUTPUT_FORMAT = "riff-16khz-16bit-mono-pcm"


logger = logging.getLogger(__name__)


def _cache_path(text: str, suffix: str) -> Path:
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{h}.{suffix}"


async def tts_it(text: str) -> Path:
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty text for TTS")

    # Prefer WAV if supported; fall back to MP3 for older edge-tts.
    suffix = "wav"
    try:
        communicate = edge_tts.Communicate(
            text=text,
            voice=VOICE_IT,
            rate="+0%",
            output_format=OUTPUT_FORMAT,
        )
    except TypeError:
        suffix = "mp3"
        communicate = edge_tts.Communicate(
            text=text,
            voice=VOICE_IT,
            rate="+0%",
        )

    out = _cache_path(text, suffix)
    if out.exists():
        logger.info("TTS cache hit: %s (%d bytes)", out, out.stat().st_size)
        return out

    if suffix == "wav":
        logger.info("TTS generating: voice=%s format=%s text=%r", VOICE_IT, OUTPUT_FORMAT, text)
    else:
        logger.info("TTS generating: voice=%s format=mp3 (fallback) text=%r", VOICE_IT, text)

    await communicate.save(str(out))

    # sanity check (avoid false negatives on very short words)
    if (not out.exists()) or out.stat().st_size < 512:
        try:
            out.unlink(missing_ok=True)
        except Exception:
            pass
        raise RuntimeError("TTS produced an empty/bad audio file")

    return out
