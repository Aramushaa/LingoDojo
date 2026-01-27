# bot/services/dictionary_it.py
from __future__ import annotations

import json
import re
from typing import Optional, Dict, Any

# We'll try requests first (most common). If not available, fallback to urllib.
try:
    import requests  # type: ignore
except Exception:
    requests = None  # type: ignore

import urllib.request
import urllib.parse


WIKTIONARY_API = "https://it.wiktionary.org/w/api.php"


def _http_get_json(url: str, params: dict) -> dict:
    """
    Small helper to GET JSON from Wiktionary.
    Adds a User-Agent to avoid 403 blocks.
    """
    headers = {
        "User-Agent": "LingoDojoBot/0.1 (learning project; contact: none)"
    }

    if requests is not None:
        r = requests.get(url, params=params, headers=headers, timeout=8)
        r.raise_for_status()
        return r.json()

    # fallback (no requests)
    qs = urllib.parse.urlencode(params)
    full = f"{url}?{qs}"
    req = urllib.request.Request(full, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))



def validate_it_title(term: str) -> dict | None:
    """
    Checks if a Wiktionary page exists for this title (with redirects).
    Returns dict with resolved title if exists, else None.
    """
    term = (term or "").strip()
    if not term:
        return None

    params = {
        "action": "query",
        "format": "json",
        "redirects": 1,
        "titles": term,
    }
    data = _http_get_json(WIKTIONARY_API, params)
    pages = data.get("query", {}).get("pages", {})
    if not pages:
        return None

    page = next(iter(pages.values()))
    if not page or "missing" in page:
        return None

    return {"title": page.get("title") or term, "pageid": page.get("pageid")}


def suggest_it_title(term: str) -> str | None:
    """
    If exact title doesn't exist, ask Wiktionary for suggestions using opensearch.
    Returns best suggestion or None.
    """
    term = (term or "").strip()
    if not term:
        return None

    params = {
        "action": "opensearch",
        "format": "json",
        "search": term,
        "limit": 1,
        "namespace": 0,
    }
    data = _http_get_json(WIKTIONARY_API, params)
    # opensearch returns: [searchterm, [titles], [descriptions], [urls]]
    if isinstance(data, list) and len(data) >= 2 and data[1]:
        return data[1][0]
    return None


def validate_it_term(term: str) -> dict:
    """
    Returns:
      {"ok": True, "title": "..."} OR
      {"ok": False, "suggestion": "..."} OR
      {"ok": False, "suggestion": None}
    """
    hit = validate_it_title(term)
    if hit:
        return {"ok": True, "title": hit["title"]}

    sug = suggest_it_title(term)
    return {"ok": False, "suggestion": sug}
