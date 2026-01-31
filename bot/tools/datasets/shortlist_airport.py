from __future__ import annotations
import csv
import os
import re
from collections import defaultdict

IN_PATH = "data/pack_sources/draft_it_a1_airport.csv"
OUT_PATH = "data/pack_sources/airport_shortlist.csv"

# Strong airport terms (high precision)
STRONG = [
    "aeroporto", "volo", "gate", "imbarco", "carta d'imbarco", "check-in",
    "passaporto", "bagaglio", "valigia", "dogana", "sicurezza", "terminal",
    "ritardo", "cancellat", "partenza", "arrivo", "passegger", "compagnia",
]

# Weak terms that cause noise (we’ll downweight)
WEAK = [
    "biglietto", "ritardo", "documenti",
]

# Hard reject topics
REJECT_IF_CONTAINS = [
    "tavolo", "gatto", "golden gate", "volo degli uccelli", "scuola",
    "treno", "autobus", "pallavolo", "basket", "forchetta", "radio",
    "penna", "biro", "libro", "diavolo",
]

def word_count(s: str) -> int:
    return len(re.findall(r"\\w+", s or ""))

def score(phrase: str) -> int:
    s = (phrase or "").lower()

    # reject obvious noise
    for bad in REJECT_IF_CONTAINS:
        if bad in s:
            return -9999

    sc = 0
    for kw in STRONG:
        if kw in s:
            sc += 10

    for kw in WEAK:
        if kw in s:
            sc += 2

    # prefer questions + polite forms
    if "?" in s:
        sc += 3
    if "per favore" in s or "scusi" in s:
        sc += 3

    # prefer short A1 friendly
    wc = word_count(s)
    if wc <= 10:
        sc += 3
    elif wc <= 14:
        sc += 1
    else:
        sc -= 4

    return sc

def bucket_tags(phrase: str) -> str:
    s = phrase.lower()
    if "passaporto" in s or "document" in s:
        return "airport,documents"
    if "check-in" in s or "carta d'imbarco" in s or "prenotazione" in s:
        return "airport,checkin"
    if "gate" in s or "imbarco" in s or "terminal" in s:
        return "airport,gate"
    if "bagaglio" in s or "valigia" in s:
        return "airport,baggage"
    if "ritardo" in s or "cancell" in s or "chiuso" in s:
        return "airport,problems"
    return "airport,mission"

def scenario_prompt_for(tags: str) -> str:
    if "documents" in tags:
        return "Mission: Passport control. Speak to the officer politely."
    if "checkin" in tags:
        return "Mission: At check-in. Ask about your boarding pass or reservation."
    if "gate" in tags:
        return "Mission: Find your gate and boarding info."
    if "baggage" in tags:
        return "Mission: Baggage drop / baggage problems."
    if "problems" in tags:
        return "Mission: Delays/cancellations. Ask what’s happening."
    return "Mission: Airport survival. Use this naturally."

def main():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    rows = []
    with open(IN_PATH, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            phrase = (row.get("phrase") or "").strip()
            meaning = (row.get("meaning_en") or "").strip()
            if not phrase or not meaning:
                continue

            sc = score(phrase)
            if sc < 8:
                continue

            row["_score"] = sc
            rows.append(row)

    # sort by score desc, then shorter phrase
    rows.sort(key=lambda x: (-int(x["_score"]), len(x["phrase"])))

    # Keep balanced buckets: max per bucket
    per_bucket_limit = 60
    buckets = defaultdict(int)
    shortlist = []

    for row in rows:
        tags = bucket_tags(row["phrase"])
        if buckets[tags] >= per_bucket_limit:
            continue

        buckets[tags] += 1
        row["tags"] = tags
        row["scenario_prompt"] = scenario_prompt_for(tags)
        row["register"] = "polite" if ("per favore" in row["phrase"].lower() or "scusi" in row["phrase"].lower()) else "neutral"
        row["risk"] = "safe"

        # leave trap/cultural/native blank for human curation
        shortlist.append(row)

        if len(shortlist) >= 250:
            break

    headers = [
        "focus","lemma","phrase","meaning_en","contexts_it","register","risk","tags",
        "scenario_prompt","trap","cultural_note","native_sauce","phrase_hint","examples_it",
        "src","tatoeba_it_id"
    ]

    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for row in shortlist:
            out = {h: row.get(h, "") for h in headers}
            w.writerow(out)

    print(f"✅ Wrote shortlist: {OUT_PATH} ({len(shortlist)} rows)")
    print("Bucket counts:")
    for k, v in sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {k}: {v}")

if __name__ == "__main__":
    main()
