import re
import unicodedata

STOPWORDS_IT = {
    "il", "lo", "la", "i", "gli", "le", "un", "una", "uno",
    "di", "a", "da", "in", "con", "su", "per", "tra", "fra",
    "e", "o", "ma", "che", "quale", "quali", "quanto", "quanti",
    "dove", "come", "quando", "perche", "perché", "cosa", "cos",
    "mi", "ti", "si", "ci", "vi", "lei", "lui", "voi", "noi", "tu", "io",
    "suo", "sua", "tuo", "tua", "vostro", "vostra", "mio", "mia",
}


def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.replace("’", "'").strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9\\s]", " ", text)
    text = re.sub(r"\\s+", " ", text).strip()
    return text


def tokens(text: str) -> list[str]:
    n = normalize(text)
    return [t for t in n.split() if t]


def build_anchors(phrase: str) -> list[str]:
    toks = tokens(phrase)
    anchors = []
    for t in toks:
        if t.isdigit():
            anchors.append(t)
            continue
        if t in STOPWORDS_IT:
            continue
        anchors.append(t)
    seen = set()
    out = []
    for a in anchors:
        if a not in seen:
            out.append(a)
            seen.add(a)
    return out


def _one_edit_away(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    i = j = edits = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
        else:
            edits += 1
            if edits > 1:
                return False
            if len(a) > len(b):
                i += 1
            elif len(b) > len(a):
                j += 1
            else:
                i += 1
                j += 1
    if i < len(a) or j < len(b):
        edits += 1
    return edits <= 1


def _anchor_hit(user_tokens: list[str], anchor: str) -> bool:
    for ut in user_tokens:
        if ut == anchor or _one_edit_away(ut, anchor):
            return True
    return False


def validate_sentence(user_sentence: str, target_phrase: str, min_hits: int = 3) -> tuple[bool, dict]:
    u_toks = tokens(user_sentence)
    anchors = build_anchors(target_phrase)

    if not anchors:
        return True, {"anchors": [], "hits": []}

    # dynamic threshold
    if len(anchors) <= 2:
        min_hits = len(anchors)
    elif len(anchors) == 3:
        min_hits = 2
    else:
        min_hits = max(min_hits, 3)

    hits = [a for a in anchors if _anchor_hit(u_toks, a)]

    # if target has numbers, require at least one number match
    nums = [a for a in anchors if a.isdigit()]
    if nums and not any(n in hits for n in nums):
        return False, {"anchors": anchors, "hits": hits, "reason": "missing_number"}

    ok = len(hits) >= min_hits
    return ok, {"anchors": anchors, "hits": hits, "min_hits": min_hits}
