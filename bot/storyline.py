from __future__ import annotations

from bot.db import get_story_progress, set_story_progress


STORY_ARCS = [
    {
        "title": "Arc 1 (A1): Noisy Neighbor",
        "level": "A1",
        "beats": [
            "Your upstairs neighbor plays loud music every night.",
            "You see a stranger leaving the building at 2 a.m.",
            "The noise stops… but now there are whispers in the hallway.",
        ],
    },
    {
        "title": "Arc 2 (A2): Suspicious Moves",
        "level": "A2",
        "beats": [
            "You spot the neighbor at the train station with a hidden bag.",
            "They slip a note under your door.",
            "The note mentions a name you don't recognize.",
        ],
    },
    {
        "title": "Arc 3 (B1): Mafia Rumor",
        "level": "B1",
        "beats": [
            "You hear a rumor: the neighbor is linked to a boss.",
            "A black car waits outside your building.",
            "You must decide: report it or stay silent.",
        ],
    },
]


def get_current_story_beat(user_id: int, user_level: str | None = None) -> dict | None:
    arc_idx, beat_idx = get_story_progress(user_id)
    if arc_idx < 0 or arc_idx >= len(STORY_ARCS):
        return None
    arc = STORY_ARCS[arc_idx]
    if user_level and (arc.get("level") or "").upper() != (user_level or "").upper():
        return {"arc_title": arc.get("title"), "text": None}
    beats = arc.get("beats") or []
    if beat_idx < 0 or beat_idx >= len(beats):
        return {"arc_title": arc.get("title"), "text": None}
    return {"arc_title": arc.get("title"), "text": beats[beat_idx]}


def advance_story(user_id: int, user_level: str | None = None):
    arc_idx, beat_idx = get_story_progress(user_id)
    if arc_idx >= len(STORY_ARCS):
        return
    arc = STORY_ARCS[arc_idx]
    if user_level and (arc.get("level") or "").upper() != (user_level or "").upper():
        return
    beats = arc.get("beats") or []
    next_beat = beat_idx + 1
    next_arc = arc_idx
    if next_beat >= len(beats):
        next_arc = arc_idx + 1
        next_beat = 0
    set_story_progress(user_id, next_arc, next_beat)
