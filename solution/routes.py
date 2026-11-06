from __future__ import annotations

import re
from collections import defaultdict

from index import STOP, words
from engine import query_groups

LINK_Q = re.compile(r"\b(links?|urls?|web ?address)\b|\bhow (?:do|can) i (?:join|sign up|enroll)\b", re.I)
ELIG_Q = re.compile(r"\beligib\w*\b.*\bmember|\bwho (?:can|may) (?:join|become)\b|\bqualify\b.*\b(?:member|join)", re.I)
CONTACT_Q = re.compile(r"\b(update|change|edit)\b.*\b(contact|phone|address|email)\b", re.I)
LINK_RE = re.compile(r"(?<!!)\[([^\]]{2,80})\]\((https?://[^)\s]+)\)")
KEEP = {"rate", "rates", "apr", "aprs", "apy", "apys", "dividend", "dividends", "interest"}
SYN_LINK = {"cd": {"certificate"}, "certificate": {"cd"}}
LINK_STOP = {"dupaco", "link", "url", "see", "use", "website", "web", "address", "should", "online", "view", "get"}
BAD_HOSTS = ("info.dupaco.com", "hubspot", "facebook", "instagram", "linkedin", "twitter", "youtube", "apple.com", "google.com")

def link_table(idx):
    """Map each distinct link to its occurrences: anchor text, page authority and the chunk's words."""
    cached = getattr(idx, "_links", None)
    if cached is not None:
        return cached
    table = defaultdict(list)
    for c in idx.chunks:
        if c.kind != "text":
            continue
        for anchor, url in LINK_RE.findall(c.text):
            if any(h in url for h in BAD_HOSTS) or "dupaco.com" not in url or re.search(r"\.(jpe?g|png|gif|svg|pdf)\b|/hubfs/", url, re.I):
                continue
            table[url].append((frozenset(words(anchor)), c.authority, c.toks))
    idx._links = table
    return table

def link_groups(question: str):
    """Question words as synonym groups, minus filler like 'link' and 'online'."""
    groups = []
    for w in words(question):
        if w in LINK_STOP or len(w) < 2 or (w in STOP and w not in KEEP):
            continue
        g = {w} | SYN_LINK.get(w, set())
        if g not in groups:
            groups.append(g)
    return groups

def link_answer(idx, question: str):
    """Answer 'what link / how do I join online' with the best-matching site link."""
    if not LINK_Q.search(question):
        return None
    groups = link_groups(question)
    if not groups:
        return None
    biz = bool(re.search(r"\bbusiness|commercial\b", question, re.I))
    ranked = []
    for url, occ in link_table(idx).items():
        path = set(words(re.sub(r"[^a-zA-Z]+", " ", url.split("dupaco.com")[-1] or "home")))
        top = None
        for anchor, auth, near in occ:
            cov = 0.0
            for g in groups:
                if g & KEEP and not (g & anchor or g & path):
                    cov = -9.0
                if g & anchor:
                    cov += 1.0
                elif g & path:
                    cov += 0.8
                elif g & near:
                    cov += 0.4
            cov /= len(groups)
            if top is None or (cov, auth) > top[:2]:
                top = (cov, auth, anchor)
        if top[0] < 0.7 or (biz is False and "/business" in url):
            continue
        key = (top[1] >= 70, round(top[0], 2), len(occ) >= 3, -url.count("/"), len(occ))
        ranked.append((key, url))
    if not ranked:
        return None
    ranked.sort(reverse=True)
    best_key, best = ranked[0]
    urls = [best] + [u for k, u in ranked[1:3] if k[:2] == best_key[:2] and k[2]]
    text = f"Use {best}" + (f" (also {urls[1]})" if len(urls) > 1 else "")
    return text, urls, best_key[1]

def contact_answer(idx, question: str):
    """Answer how to update contact details from the contact page: Shine plus the main phone line."""
    if not CONTACT_Q.search(question):
        return None
    for url, chunks in idx.page_text.items():
        if url.rstrip("/").endswith("/contact") and chunks:
            text = " ".join(chunks)
            phone = re.search(r"\b\d{3}-\d{3}-\d{4}\b", text)
            if phone:
                msg = (f"Log in to Shine Online or Mobile Banking and use the Contact Us tab, "
                       f"or call Dupaco at {phone.group(0)}.")
                return msg, [url], 1.0
    return None

def eligibility_answer(idx, question: str):
    """Answer membership eligibility: the live-or-work rule plus the counties Dupaco serves."""
    if not ELIG_Q.search(question):
        return None
    rule = area = None
    for c in idx.chunks:
        if c.kind != "text":
            continue
        if re.search(r"live or work", c.text, re.I) and re.search(r"charter area", c.text, re.I):
            if rule is None or c.authority > rule.authority:
                rule = c
        if re.search(r"counties", c.text) and re.search(r"Iowa", c.text) and re.search(r"Wisconsin", c.text) and re.search(r"serves|residents|live", c.text, re.I):
            if area is None or (c.authority, -len(c.text)) > (area.authority, -len(area.text)):
                area = c
    if not (rule and area):
        return None
    msg = f"{rule.text.lstrip('- ').strip()} {area.text.strip()}"
    return msg[:760], [rule.url, area.url], 1.0