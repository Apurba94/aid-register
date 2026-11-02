"""Registration logic: entitlements, double collection and fuzzy duplicate detection.

Names are spelled many ways in transliteration, so exact matching misses real duplicates, and
loose matching wrongly accuses real families. This module suggests pairs for a person to review.
It never merges or removes anyone by itself.
"""
import re
import unicodedata
from dataclasses import dataclass

TITLES = {"md", "mohammad", "mohammed", "muhammad", "mohd", "mst", "mosammat", "mrs", "mr", "sk", "sheikh", "shaikh"}
SPELLING = [("ph", "f"), ("th", "t"), ("kh", "k"), ("gh", "g"), ("sh", "s"), ("dh", "d"), ("bh", "b"), ("ee", "i"), ("oo", "u"), ("ou", "u"), ("aa", "a"), ("w", "o"), ("y", "i"), ("q", "k")]


@dataclass
class Household:
    id: int
    head: str
    members: int
    phone: str = ""
    block: str = ""
    birth_year: int = 0
    father: str = ""


def jaro(a, b):
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    if not la or not lb:
        return 0.0
    window = max(la, lb) // 2 - 1
    ma, mb = [False] * la, [False] * lb
    matches = 0
    for i, c in enumerate(a):
        for j in range(max(0, i - window), min(lb, i + window + 1)):
            if not mb[j] and b[j] == c:
                ma[i] = mb[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    k = trans = 0
    for i in range(la):
        if ma[i]:
            while not mb[k]:
                k += 1
            trans += a[i] != b[k]
            k += 1
    m = matches
    return (m / la + m / lb + (m - trans / 2) / m) / 3


def jaro_winkler(a, b, p=0.1):
    j = jaro(a, b)
    if j <= 0.7:
        return j
    l = 0
    for x, y in zip(a[:4], b[:4]):
        if x != y:
            break
        l += 1
    return j + l * p * (1 - j)


def normalise(name):
    """Lower-case, drop accents and titles, and even out common transliteration differences."""
    text = unicodedata.normalize("NFKD", name.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    words = [w for w in re.split(r"[^\w]+", text) if w and w not in TITLES]
    out = []
    for w in words:
        for x, y in SPELLING:
            w = w.replace(x, y)
        w = re.sub(r"(.)\1+", r"\1", w)
        out.append(w)
    return out


def name_score(a, b):
    """Match word against word, in any order, so 'Rahima Begum' meets 'Begum Rahima'."""
    wa, wb = normalise(a), normalise(b)
    if not wa or not wb:
        return 0.0
    if len(wa) > len(wb):
        wa, wb = wb, wa
    total = 0.0
    left = list(wb)
    for w in wa:
        best = max(left, key=lambda x: jaro_winkler(w, x))
        total += jaro_winkler(w, best)
        left.remove(best)
    return total / len(wa) * (0.9 + 0.1 * len(wa) / len(wb))


def clean_phone(p):
    d = re.sub(r"\D", "", p)
    return d[-10:] if len(d) >= 10 else d


def pair_score(a, b):
    """Evidence that two records are one household, from 0 to 1, with the reasons."""
    score = name_score(a.head, b.head)
    reasons = [f"names {score:.0%} alike"]
    pa, pb = clean_phone(a.phone), clean_phone(b.phone)
    if pa and pa == pb:
        score = min(1.0, score + 0.2)
        reasons.append("same phone")
    if a.father and b.father:
        f = name_score(a.father, b.father)
        if f >= 0.85:
            score = min(1.0, score + 0.1)
            reasons.append("same father's name")
        elif f < 0.6:
            score -= 0.2
            reasons.append("different father's name")
    if a.birth_year and b.birth_year:
        gap = abs(a.birth_year - b.birth_year)
        if gap > 5:
            score -= 0.25
            reasons.append(f"{gap} years apart in age")
    return score, reasons


def blocks(records):
    """Group records so that only likely pairs are compared. This keeps large registers fast."""
    groups = {}
    for r in records:
        keys = {w[:2] for w in normalise(r.head) if len(w) >= 2}
        phone = clean_phone(r.phone)
        if phone:
            keys.add("p" + phone)
        for k in keys:
            groups.setdefault(k, []).append(r)
    return groups


def find_duplicates(records, threshold=0.88):
    """Return candidate pairs, strongest first: (score, id a, id b, reasons)."""
    seen = set()
    out = []
    for group in blocks(records).values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                key = (min(a.id, b.id), max(a.id, b.id))
                if key in seen:
                    continue
                seen.add(key)
                s, why = pair_score(a, b)
                if s >= threshold:
                    out.append((s, key[0], key[1], why))
    return sorted(out, key=lambda t: (-t[0], t[1], t[2]))


def entitlement(members, ration):
    """ration: list of (item, base quantity, per person, cap or None). Returns {item: quantity}."""
    if members < 1:
        raise ValueError("a household has at least one member")
    out = {}
    for item, base, per, cap in ration:
        q = base + per * members
        out[item] = min(q, cap) if cap is not None else q
    return out


def round_totals(households, ration):
    """Total stock needed for a distribution round, for ordering before the day."""
    totals = {}
    for h in households:
        for item, q in entitlement(h.members, ration).items():
            totals[item] = totals.get(item, 0) + q
    return totals
