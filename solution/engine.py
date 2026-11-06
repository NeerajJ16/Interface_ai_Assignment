"""Question -> chunks -> one clean answer (or an honest refusal)."""
from __future__ import annotations

import math
import re
from collections import OrderedDict

from index import (row_key, RE_MODEL, RE_MONTHS, RE_YEARS, STOP, SYN, Chunk, SnapshotIndex, bigrams, model_range,
                    parse_quals, stem, tier_of, words)

RATE_WORDS = re.compile(r"\b(rates?|apr|apy|interest|dividends?|percent|percentage)\b", re.I)
RE_ROW_MONTHS = re.compile(r"(?<![\d.])(\d{1,3})\s*[- ]?\s*(?:months?|mos?)\b", re.I)
RE_ROW_YEARS = re.compile(r"(?<![\d.])(\d{1,2})\s*[- ]?\s*(?:year|yr)\b", re.I)
ACCEPT = 0.50            
REFUSAL = ("I don't know - that isn't listed on the Dupaco website. "
           "Please contact Dupaco directly or visit a branch for help.")


def query_groups(question: str):
    """Distinctive question words (qualifier numbers removed), each as a set of acceptable stems."""
    q = RE_MONTHS.sub(" ", question)
    q = RE_YEARS.sub(" ", q)
    q = RE_MODEL.sub(" ", q)
    q = re.sub(r"\$\s*[\d,.]+", " ", q)
    groups, seen = [], set()
    for w in words(q):
        if w in STOP or w in seen or w.isdigit():
            continue
        seen.add(w)
        groups.append(set(SYN.get(w, set())) | {w})
    return groups


def row_checks(c: Chunk, quals):
    """(matches, mismatches) of a row against the question's qualifiers."""
    pos = neg = 0
    text = f"{c.heading} {c.label}"
    if quals.months:
        have = {int(x) for x in RE_ROW_MONTHS.findall(text)}
        if have:
            pos, neg = (pos + 1, neg) if quals.months & have else (pos, neg + 1)
    if quals.years:
        have = {int(x) for x in RE_ROW_YEARS.findall(text)}
        if have:
            pos, neg = (pos + 1, neg) if quals.years & have else (pos, neg + 1)
    if quals.model:
        r = model_range(text)
        if r:
            pos, neg = (pos + 1, neg) if any(r[0] <= y <= r[1] for y in quals.model) else (pos, neg + 1)
    if quals.amounts:
        t = tier_of(c.label)
        if t:
            a = quals.amounts[0]
            pos, neg = (pos + 1, neg) if t[0] <= a <= t[1] else (pos, neg + 1)
    return pos, neg


TIME = re.compile(r"\d{1,2}(?::\d{2})?\s*(?:a\.?m|p\.?m)\b|\bnoon\b", re.I)
STREET = re.compile(r"\d+\s+[A-Za-z0-9. ]+?\b(?:ln|lane|st|street|ave|avenue|rd|road|blvd|dr|drive|hwy|way|pkwy|ct|court)\b", re.I)
URLISH = re.compile(r"https?://|dupaco\.com", re.I)


def required_evidence(question: str):
    """Regexes a chunk must match to be able to answer this kind of question."""
    q = question.lower()
    need = []
    if re.search(r"\b(hours?|lobby|drive[- ]?up)\b", q):
        need.append(TIME)
    elif re.search(r"\b(open|opens|close|closes|closing|closed)\b", q):
        need.append(re.compile(r"\d"))
    if re.search(r"\b(address|located|location of)\b", q):
        need.append(STREET)
    if re.search(r"\b(link|url|website|web address|site)\b", q):
        need.append(URLISH)
    if re.search(r"\b(routing|phone|call)\b", q):
        need.append(re.compile(r"\d"))
    m = re.search(r"\bhow many (?:\w+ ){0,2}?([a-z]{4,})", q)
    if m:                                    
        noun = stem(m.group(1))
        need.append(re.compile(rf"\b\d[\d,]*\s+(?:[\w-]+\s+){{0,1}}{re.escape(noun)}", re.I))
    return need


NEEDS_DIGITS = re.compile(r"\b(address|number|phone|call|hours?|when|how many|how much|zip|routing|open|close|"
                          r"date|branches|employees|percent)\b", re.I)


def proper_nouns(question: str):
    """Stems of capitalised words that are not the first word - the entity the question is about."""
    toks = re.findall(r"[A-Za-z][A-Za-z'-]*", question)
    out = set()
    for i, w in enumerate(toks):
        if i and w[0].isupper() and w.lower() not in ("dupaco", "i", "i'm", "ach", "atm"):
            out.update(words(w))
    return {w for w in out if w not in STOP}


def score_chunks(idx: SnapshotIndex, groups, quals, question: str):
    wts = [(max((idx.idf.get(t, 0.0) for t in g), default=1.0) or 1.0) ** 2 for g in groups] 
    total = sum(wts) or 1.0
    qbis = bigrams(question)
    want_digits = bool(NEEDS_DIGITS.search(question))
    caps = proper_nouns(question)
    scored = []
    for c in idx.chunks:
        cov = 0.0
        for g, w in zip(groups, wts):
            hit = g & c.toks
            if hit:
                cov += w * (0.6 + 0.4 * len(hit) / len(g))
        cov /= total
        if cov == 0:
            continue
        s = cov + (0.25 if caps and caps <= c.toks else 0.0) + 0.30 * min(len(qbis & c.bis), 2) - 0.07 * math.log2(1 + len(c.toks) / 12)
        s += 0.15 * c.authority / 100 - (0.20 if c.carried else 0)
        if c.kind == "row":
            pos, neg = row_checks(c, quals)
            s += 0.25 * pos - 0.6 * neg
            if re.search(r"refinanc|equity", f"{c.heading} {c.label}", re.I) and not re.search(r"refi|equity|heloc", question, re.I):
                s -= 0.12
        else:
            if want_digits and re.search(r"\d", c.text):
                s += 0.15
            if "Keep reading" in c.text:      
                s -= 0.15
            if c.text.startswith("DUBUQUE"):   
                s += 0.06
            if c.pub:                        
                s += 0.03 * min(max((int(c.pub[:4]) * 12 + int(c.pub[5:7]) - 2022 * 12) / 58, 0.0), 1.0)
        scored.append((s, cov, c))
    scored.sort(key=lambda x: (-x[0], x[2].url, x[2].order))
    return scored, wts


def tidy_ladders(rows):
    """For 'X or less' loan-amount ladders keep the smallest (headline) and largest tier per program."""
    ladders = OrderedDict()
    for c in rows:
        if re.search(r"or less", c.label, re.I):
            key = re.sub(r"\$[\d,.]+\s*or less", "", c.label).strip()
            ladders.setdefault(key, []).append(c)
    drop = set()
    for key, cs in ladders.items():
        cs.sort(key=lambda c: tier_of(c.label)[1])
        for c in cs[1:-1]:
            drop.add(id(c))
    return [c for c in rows if id(c) not in drop]


def select_rows(rows, quals):
    """Narrow a table to the rows the question's qualifiers point at."""
    rows = list(rows)
    for kind in ("months", "years", "model"):
        want = getattr(quals, kind)
        if not want:
            continue
        keep = []
        for c in rows:
            ck = type(quals)(**{kind: want})
            p, n = row_checks(c, ck)
            if p and not n:
                keep.append(c)
        if keep:
            rows = keep
    if quals.amounts:
        a = quals.amounts[0]
        hits = [(tier_of(c.label), c) for c in rows if tier_of(c.label) and tier_of(c.label)[0] <= a <= tier_of(c.label)[1]]
        if hits:
            tightest = {}
            for t, c in hits:
                key = re.sub(r"\$[\d,.]+(?:\s*[-–]\s*\$?[\d,.]+)?\+?|or less", "", c.label).strip()
                if key not in tightest or (t[1] - t[0]) < tightest[key][0]:
                    tightest[key] = (t[1] - t[0], c)
            rows = [c for _, c in tightest.values()]
    else:
        rows = tidy_ladders(rows)
    return rows


def arbitrate(idx: SnapshotIndex, c: Chunk) -> Chunk:
    """Same fact on several pages: the most authoritative, freshest page supplies the value."""
    peers = idx.same_row.get(row_key(c.heading, c.label), [c])
    return max(peers, key=lambda p: (p.authority, not p.carried, p.url))


def render_row(c: Chunk) -> str:
    label = c.label
    if c.heading and c.heading.lower() not in label.lower():
        label = f"{c.heading} - {label}"
    return f"{label}: {c.metrics}" if c.metrics else label


def attempt(idx: SnapshotIndex, question: str):
    groups = query_groups(question)
    if not groups:
        return None
    quals = parse_quals(question)
    rate_q = bool(RATE_WORDS.search(question))
    scored, wts = score_chunks(idx, groups, quals, question)
    if not scored:
        return None

    need = required_evidence(question)

    def eligible(c):
        if c.kind == "row":
            if rate_q:
                return bool(c.metrics)
            return all(r.search(f"{c.label} {c.metrics}") for r in need) if need else bool(c.metrics) or True
        if rate_q and "%" not in c.text:
            return False
        return all(r.search(c.text) for r in need)

    best_row = next((x for x in scored if x[2].kind == "row" and eligible(x[2])), None)
    best_txt = next((x for x in scored if x[2].kind == "text" and eligible(x[2])), None)

    pick = None
    if re.search(r"\bhow many\b", question.lower()) and best_txt:
        near = [x for x in scored if x[2].kind == "text" and eligible(x[2]) and x[1] >= best_txt[1] - 0.1 and x[2].pub]
        if near:
            pick = max(near, key=lambda x: (x[2].pub, x[0]))
    if pick:
        pass
    elif rate_q and best_row and best_row[1] >= ACCEPT:
        pick = best_row
    elif best_row and best_txt:
        pick = best_row if best_row[0] >= best_txt[0] and best_row[1] >= ACCEPT else (best_txt if best_txt[1] >= ACCEPT else None)
    elif best_row and best_row[1] >= ACCEPT:
        pick = best_row
    elif best_txt and best_txt[1] >= ACCEPT:
        pick = best_txt
    if not pick:
        return None

    top, cov, c = pick
    if c.kind == "row":
        tables, seen = [c], {c.table_id}
        for sc, _, r in scored:
            if sc < top - 0.08 or len(tables) >= 4:
                break
            if r.kind == "row" and eligible(r) and r.table_id not in seen and not any((quals.months, quals.years, quals.model, quals.amounts)):
                seen.add(r.table_id)
                tables.append(r)
        out, urls, shown = [], [], set()
        for t in tables:
            for r in select_rows(idx.tables[t.table_id], quals)[:8]:
                r = arbitrate(idx, r)
                line = render_row(r)
                if line not in shown:
                    shown.add(line)
                    out.append(line)
                    # cite every official page that carries this exact value
                    for peer in sorted(idx.same_row.get(row_key(r.heading, r.label), [r]), key=lambda p: -p.authority):
                        if peer.metrics == r.metrics and peer.authority >= 80 and not peer.carried and peer.url not in urls:
                            urls.append(peer.url)
                    if r.url not in urls:
                        urls.append(r.url)
        return "\n".join(out[:10]), urls[:4], cov
    text = c.text
    nxt = idx.page_text.get(c.url, [])
    if c.order + 1 < len(nxt) and len(text) + len(nxt[c.order + 1]) <= 760:
        text = f"{text} {nxt[c.order + 1]}"          
    return text[:760], [c.url], cov