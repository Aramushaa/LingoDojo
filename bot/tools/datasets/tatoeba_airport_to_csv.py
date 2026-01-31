from __future__ import annotations
import csv
import os
import re
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

RAW_SENTENCES = "data/tatoeba/raw/sentences.csv"
RAW_LINKS = "data/tatoeba/raw/links.csv"
OUT_DRAFT = "data/pack_sources/draft_it_a1_airport.csv"

TARGET_LANG = "ita"
TRANSL_LANG = "eng"

# Airport-ish keywords (MVP). We can expand later.
AIRPORT_KEYWORDS = [
    "aeroporto", "volo", "gate", "imbarco", "carta d'imbarco", "check-in",
    "bagaglio", "valigia", "passaporto", "documenti", "controlli", "sicurezza",
    "dogana", "ritardo", "partenza", "arrivo", "terminal", "biglietto"
]

def normalize(s: str) -> str:
    return (s or "").strip()

def contains_keyword(it_sentence: str) -> bool:
    s = it_sentence.lower()
    return any(k in s for k in AIRPORT_KEYWORDS)

def load_sentences(path: str) -> Dict[int, Tuple[str, str]]:
    """
    sentences.csv format: id \t lang \t text
    """
    out: Dict[int, Tuple[str, str]] = {}
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) < 3:
                continue
            sid = int(row[0])
            lang = row[1]
            text = row[2]
            out[sid] = (lang, text)
    return out

def load_links(path: str) -> List[Tuple[int, int]]:
    """
    links.csv format: id1 \t id2
    (bidirectional-ish; we’ll treat as undirected)
    """
    pairs: List[Tuple[int, int]] = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) < 2:
                continue
            a = int(row[0]); b = int(row[1])
            pairs.append((a, b))
    return pairs

def build_translation_map(
    sentences: Dict[int, Tuple[str, str]],
    links: List[Tuple[int, int]],
    src_lang: str,
    tgt_lang: str
) -> Dict[int, List[int]]:
    """
    Map src sentence id -> list of tgt sentence ids.
    """
    m: Dict[int, List[int]] = defaultdict(list)
    for a, b in links:
        la = sentences.get(a, ("", ""))[0]
        lb = sentences.get(b, ("", ""))[0]
        if la == src_lang and lb == tgt_lang:
            m[a].append(b)
        elif la == tgt_lang and lb == src_lang:
            m[b].append(a)
    return m

def pick_best_english(
    eng_ids: List[int],
    sentences: Dict[int, Tuple[str, str]]
) -> Optional[str]:
    # MVP heuristic: pick the shortest English translation (usually cleaner)
    best = None
    for eid in eng_ids:
        text = sentences.get(eid, ("", ""))[1]
        if not text:
            continue
        if best is None or len(text) < len(best):
            best = text
    return best

def main():
    os.makedirs(os.path.dirname(OUT_DRAFT), exist_ok=True)

    print("Loading sentences...")
    sentences = load_sentences(RAW_SENTENCES)
    print(f"Sentences loaded: {len(sentences)}")

    print("Loading links...")
    links = load_links(RAW_LINKS)
    print(f"Links loaded: {len(links)}")

    ita_to_eng = build_translation_map(sentences, links, TARGET_LANG, TRANSL_LANG)

    # Collect candidates
    rows_out = []
    it_total = 0
    it_with_keyword = 0
    it_with_translation = 0
    for sid, (lang, it_text) in sentences.items():
        if lang != TARGET_LANG:
            continue
        it_total += 1
        it_text = normalize(it_text)
        if not it_text:
            continue
        if not contains_keyword(it_text):
            continue
        it_with_keyword += 1

        eng_ids = ita_to_eng.get(sid, [])
        eng_text = pick_best_english(eng_ids, sentences)
        if not eng_text:
            continue
        it_with_translation += 1

        # Minimal pack-factory columns
        # focus=phrase because these are sentence-based mission items.
        rows_out.append({
            "focus": "phrase",
            "lemma": "",
            "phrase": it_text,
            "meaning_en": normalize(eng_text),
            "contexts_it": it_text,   # start with itself; you can later add more contexts
            "register": "neutral",
            "risk": "safe",
            "tags": "airport,mission",
            "scenario_prompt": "You are at the airport. Use this naturally.",
            "trap": "",
            "cultural_note": "",
            "native_sauce": "",
            "phrase_hint": "",
            "examples_it": "",
            # attribution (extra columns, safe to keep)
            "src": "tatoeba",
            "tatoeba_it_id": str(sid)
        })

    # De-dup by phrase text
    dedup = {}
    for r in rows_out:
        key = r["phrase"].strip().lower()
        dedup[key] = r
    rows_out = list(dedup.values())

    # Write CSV
    headers = [
        "focus","lemma","phrase","meaning_en","contexts_it","register","risk","tags",
        "scenario_prompt","trap","cultural_note","native_sauce","phrase_hint","examples_it",
        "src","tatoeba_it_id"
    ]

    with open(OUT_DRAFT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows_out:
            w.writerow(r)

    print(f"✅ Draft written: {OUT_DRAFT} ({len(rows_out)} rows)")
    print(f"Debug: it_total={it_total}, it_with_keyword={it_with_keyword}, it_with_translation={it_with_translation}")
    print("Next: open draft CSV, curate, then run pack factory -> JSON -> /reloadpacks")

if __name__ == "__main__":
    main()
