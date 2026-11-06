"""Chunk index + qualifier-aware retrieval."""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field

_FOOT_PCT = re.compile(r"(\d%)\d\b")
_FOOT_LBL = re.compile(r"\b(APR|APY)\d\b")
_FOOT_HDR = re.compile(r"(?<=[A-Za-z\)])\d$")

def tidy(s: str) -> str:
    s = _FOOT_PCT.sub(r"\1", s)
    s = _FOOT_LBL.sub(r"\1", s)
    return s.strip()

def tidy_header(h: str) -> str:
    h = _FOOT_HDR.sub("", h.strip())
    h = h.replace("Annual Percentage Yield (APY)", "APY").replace("Annual Percentage Rate", "APR")
    return h.replace("(As Low As)", "(as low as)").strip()

_WORD = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*")
STOP = set("""a an the is are was were be been do does did can could would should will you your yours i me my we our us
it its this that these those of to in on at for from by with about as and or but if then so what whats which who whom
how when where why there here have has had get give tell show want like need know please any some all just also
than into over under per not no yes more most very much many current currently right now today latest new
dupaco union rate rates apr apy interest dividend percent percentage yield annual offer offers offered
available option options use used using up highest lowest best top maximum minimum provide between earn charge receive received their""".split())

SYN = {
    "mortgage": {"mortgage", "home", "purchase", "refinance"},
    "cd": {"certificate"}, "cds": {"certificate"}, "certificates": {"certificate"},
    "car": {"auto"}, "vehicle": {"auto", "vehicle"}, "motorcycle": {"motorcycle"},
    "boat": {"boat", "rv"}, "rv": {"boat", "rv"},
    "card": {"card", "visa"}, "cards": {"card", "visa"},
    "wallet": {"wallet", "apple", "google", "samsung"},
    "lobby": {"lobby"}, "hours": {"hours", "hour"},
}

_Z = (("ition", "ize"), ("izing", "ize"), ("ized", "ize"), ("izes", "ize"), ("ization", "ize"))

def stem(w: str) -> str:
    if w in STOP:
        return w
    if len(w) > 4 and re.search(r"(ch|sh|x|ss|z)es$", w):
        return w[:-2]
    for suf, rep in _Z:
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)] + rep
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w

def words(text: str) -> list:
    return [stem(w.strip(".,")) for w in _WORD.findall(text.lower())]

def bigrams(text: str) -> frozenset:
    w = [t for t in words(text) if t not in STOP]
    return frozenset(zip(w, w[1:]))

_AMT = r"\$\s*([\d,]+(?:\.\d+)?)"
RE_MONTHS = re.compile(r"(?<![\d.])(\d{1,3})\s*[- ]?\s*(?:months?|mos?)\b", re.I)
RE_YEARS = re.compile(r"(?<![\d.])(\d{1,2})\s*[- ]?\s*(?:year|yr)\b", re.I)
RE_MODEL = re.compile(r"(20\d\d)\s*(?:model|vehicle|car|truck|auto|suv|motorcycle)", re.I)
RE_RANGE_YEARS = re.compile(r"(20\d\d)\s*[-–]\s*(\d{2,4})")
RE_TIER_RANGE = re.compile(_AMT + r"\s*[-–]\s*\$?\s*([\d,]+(?:\.\d+)?)")
RE_TIER_PLUS = re.compile(_AMT + r"\s*\+")
RE_TIER_LESS = re.compile(_AMT + r"\s*(?:or less|and under)", re.I)

def _f(x: str) -> float:
    return float(x.replace(",", ""))

@dataclass
class Quals:
    months: set = field(default_factory=set)
    years: set = field(default_factory=set)
    model: set = field(default_factory=set)
    amounts: list = field(default_factory=list)

def parse_quals(q: str) -> Quals:
    out = Quals()
    out.months = {int(m) for m in RE_MONTHS.findall(q)}
    out.years = {int(m) for m in RE_YEARS.findall(q)}
    out.model = {int(m) for m in RE_MODEL.findall(q)}
    out.amounts = sorted(_f(m) for m in re.findall(_AMT, q))
    return out

def tier_of(label: str):
    """(lo, hi) balance / loan-amount tier named in a row label, else None."""
    m = RE_TIER_PLUS.search(label)
    if m:
        return (_f(m.group(1)), math.inf)
    m = RE_TIER_RANGE.search(label)
    if m:
        return (_f(m.group(1)), _f(m.group(2)))
    m = RE_TIER_LESS.search(label)
    if m:
        return (0.0, _f(m.group(1)))
    return None

def model_range(label: str):
    m = RE_RANGE_YEARS.search(label)
    if not m:
        return None
    a, b = int(m.group(1)), m.group(2)
    b = int(b) if len(b) == 4 else int(m.group(1)[:2] + b)
    return (min(a, b), max(a, b))

RATE_HDR = re.compile(r"rate|apr|apy|yield|point|payment|min\.", re.I)

MONTHS = {m: i for i, m in enumerate("January February March April May June July August September October November December".split(), 1)}
RE_PUBDATE = re.compile(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2}),\s+(20\d\d)\b")

def pub_date(text: str) -> str:
    """ISO date of a dated article (first 'Month DD, YYYY' near the top), else ''."""
    m = RE_PUBDATE.search(text[:700])
    return f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}" if m else ""

@dataclass
class Chunk:
    kind: str
    url: str
    snap: int
    text: str
    toks: frozenset
    authority: int
    carried: bool
    table_id: str = ""
    heading: str = ""
    label: str = ""
    metrics: str = ""
    order: int = 0
    bis: frozenset = frozenset()
    pub: str = ""

def row_chunk(pv, snap_i, t, ti, ri, row) -> Chunk:
    label_parts, metric_parts = [], []
    for h, v in row.items():
        v = tidy(v)
        if not v or v in ("—", "-"):
            continue
        hh = tidy_header(h)
        if re.match(r"(?i)min\.|\\?\*?\s*payment", hh) or hh.lower() == "points":
            continue
        if re.search(r"(?i)rate|apr|apy|yield", hh) and re.search(r"\d", v):
            metric_parts.append(f"{hh} {v}")
        else:
            label_parts.append(v)
    label = ", ".join(label_parts)
    metrics = ", ".join(metric_parts)
    pageword = pv.url.split("dupaco.com")[-1].replace("-", " ").replace("/", " ")
    hdrs = " ".join(tidy_header(h) for h in row)
    blob = f"{t.heading} {label} {metrics} {hdrs} {pageword} {pv.title}"
    toks = frozenset(words(blob))
    return Chunk("row", pv.url, snap_i, f"{label}: {metrics}" if metrics else label, toks,
                 pv.authority, pv.carried_forward, f"{pv.url}#{ti}", t.heading, label, metrics, ri,
                 bigrams(t.heading) | bigrams(label) | bigrams(hdrs))

def text_chunks(pv, snap_i):

    prose = "\n".join(l for l in pv.text.split("\n") if not l.lstrip().startswith("|"))
    out, order = [], 0
    pageword = pv.url.split("dupaco.com")[-1].replace("-", " ").replace("/", " ")
    pub = pub_date(pv.text)
    for para in re.split(r"\n\s*\n", prose):
        units = []
        for line in para.split("\n"):
            line = tidy(re.sub(r"\s+", " ", line)).strip()
            if len(line) < 3:
                continue
            units.extend(x for x in re.split(r"(?<=[.!?])\s+", line) if x)
        pieces, cur = [], ""
        for u in units:
            if cur and len(cur) + len(u) > 420:
                pieces.append(cur)
                cur = u
            else:
                cur = f"{cur} {u}".strip()
        if cur:
            pieces.append(cur)
        for p in pieces:
            if len(p) < 25:
                continue
            toks = frozenset(words(f"{p} {pageword} {pv.title}"))
            out.append(Chunk("text", pv.url, snap_i, p, toks, pv.authority, pv.carried_forward,
                             order=order, bis=bigrams(p), pub=pub))
            order += 1
    return out

TIER = re.compile(r"\$[\d,.]+(?:\s*[-\u2013]\s*\$?[\d,.]+)?\+?|or less")

GENERIC_HEADING = {"account", "accounts", "certificate", "certificates", "rate", "rates", "business"}

def fact_key(c, bands: dict, tier: bool = True):
    """Identity of a fact row across pages and snapshots: product + program/tier + audience."""
    base = re.sub(r"\baccounts?\b", "", c.heading, flags=re.I).strip()
    label = c.label if tier else TIER.sub("", c.label)
    if base:
        label = re.sub(r"^\s*" + re.escape(base) + r"\s*[,:-]?\s*", "", label, flags=re.I)
    m = RE_RANGE_YEARS.search(label)
    if m:
        label = label.replace(m.group(0), f"BAND{bands.get(m.group(0), 0)}")
    alpha = len(re.findall(r"[A-Za-z]{3,}", label))
    core = [w for w in re.findall(r"[a-z]+", base.lower()) if w not in GENERIC_HEADING]
    hk = core[0] if core and alpha <= 2 else ""
    aud = "biz" if "/business" in c.url or "business" in c.heading.lower() else "per"
    return (re.sub(r"[^a-z0-9]", "", label.lower()), hk, aud)

def row_key(heading: str, label: str) -> str:
    """Identity of a fact row regardless of page: product + program/tier, punctuation-free."""
    return re.sub(r"[^a-z0-9]", "", f"{label}".lower())

RE_HOURS = re.compile(r"\*\*Lobby\*\*(.*?)\*\*Drive-up\*\*(.*?)(?=\*\*ABOUT|\Z)", re.S | re.I)
RE_BRANCH_NAME = re.compile(r"(?:[Tt]he|for the)\s+((?:[A-Z][\w.']*\s+){0,3}?(?:Learning Lab|learning lab|branch))")
RE_ADDR = re.compile(r"^\d+\s.+,\s*[A-Z]{2},\s*\d{5}$")

def _schedule(block: str) -> str:
    rows = [re.sub(r"\s+", " ", l).strip(" *|") for l in block.split("\n")]
    return "; ".join(r for r in rows if r and not r.lower().startswith(("branch hours", "**")))

def hours_blocks(pv):
    """Lobby / drive-up schedules announced for a branch, with the branch they belong to."""
    out = []
    for m in RE_HOURS.finditer(pv.text):
        before = pv.text[max(0, m.start() - 700): m.start()]
        names = RE_BRANCH_NAME.findall(before)
        branch = re.sub(r"\s+branch$", "", names[-1].strip(), flags=re.I) if names else pv.title
        if branch.lower().endswith("learning lab"):
            branch = pv.title
        for kind, block in (("Lobby", m.group(1)), ("Drive-up", m.group(2))):
            sched = _schedule(block)
            if sched:
                out.append((kind, branch, sched, pub_date(pv.text), pv.url))
    return out

def location_chunks(pv, snap_i):
    """One fact per locator entry on a page listing branches / ATMs with street addresses."""
    out = []
    for block in re.split(r"\n###\s+", pv.text)[1:]:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        addr = next((l for l in lines[1:4] if RE_ADDR.match(l)), None)
        if not addr:
            continue
        kind = lines[1] if lines[1] != addr else "Location"
        services = next((l for l in lines if "·" in l), "")
        text = f"{lines[0]} - {kind} address: {addr}." + (f" Services: {services}." if services else "")
        out.append(Chunk("text", pv.url, snap_i, text, frozenset(words(f"{text} {pv.title}")), pv.authority,
                         pv.carried_forward, order=10000 + len(out), bis=bigrams(text)))
    return out

class SnapshotIndex:
    def __init__(self, snap_id, taken_on):
        self.snap_id, self.taken_on = snap_id, taken_on
        self.chunks = []
        self.tables = defaultdict(list)
        self.bands = {}
        self.same_row = defaultdict(list)
        self.page_text = defaultdict(list)
        self.hours = []
        self.idf = {}

    def finalize(self):
        df = defaultdict(int)
        for c in self.chunks:
            for t in c.toks:
                df[t] += 1
        n = max(len(self.chunks), 1)
        self.idf = {t: math.log(1 + n / d) for t, d in df.items()}
        for c in self.chunks:
            m = c.kind == "row" and RE_RANGE_YEARS.search(c.label)
            if m:
                b = self.bands.setdefault(c.table_id, {})
                b.setdefault(m.group(0), len(b))
        for c in self.chunks:
            if c.kind == "text":
                self.page_text[c.url].append(c.text)
            if c.kind == "row":
                self.tables[c.table_id].append(c)
                self.same_row[fact_key(c, self.bands.get(c.table_id, {}))].append(c)