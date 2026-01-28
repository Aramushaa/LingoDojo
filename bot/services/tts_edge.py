# bot/services/tts_edge.py
from __future__ import annotations

import os
from pathlib import Path
import hashlib
import edge_tts

CACHE_DIR = Path("bot_cache/tts")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

VOICE_IT = os.getenv("TTS_VOICE_IT", "it-IT-DiegoNeural")

# ✅ WAV PCM (most compatible with Telegram)
OUTPUT_FORMAT = "riff-24khz-16bit-mono-pcm"


def _cache_path(text: str) -> Path:
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{h}.wav"


async def tts_it(text: str) -> Path:
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty text for TTS")

    out = _cache_path(text)
    if out.exists():
        return out

    communicate = edge_tts.Communicate(text=text, voice=VOICE_IT, rate="+0%")
    await communicate.save(str(out))

    # sanity check
    if (not out.exists()) or out.stat().st_size < 2000:
        try:
            out.unlink(missing_ok=True)
        except Exception:
            pass
        raise RuntimeError("TTS produced an empty/bad audio file")

    return out
