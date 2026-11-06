"""Versioned page store + markdown table parser.

Keeps EVERY version of every page (url x snapshot) so `as_of` queries can be answered
from the website as it stood on a given day, and so conflicts can be found across time.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


def clean(text: str) -> str:
    """Normalise junk seen in the crawl (literal \\r\\n, nbsp, footnote glue)."""
    text = text.replace("\\\\r\\\\n", "\n").replace("\\r\\n", "\n")
    return text.replace("\xa0", " ")


@dataclass
class Table:
    heading: str                 # nearest non-table line above the table (section label)
    header: list                 # column names
    rows: list                   # list of dicts {column: cell}
    context: str = ""            # a few lines of text above, for product naming


@dataclass
class PageVersion:
    url: str
    snapshot_id: str
    taken_on: str                # snapshot date (ISO)
    fetched_at: str              # when this page copy was really downloaded
    title: str
    text: str                    # cleaned markdown
    authority: int
    carried_forward: bool        # page copy older than the snapshot => likely stale
    tables: list = field(default_factory=list)


def authority(url: str) -> int:
    """How much we trust a URL as the source of a *current* fact (0-100)."""
    path = url.split("dupaco.com", 1)[-1].split("#")[0].split("?")[0].rstrip("/")
    if path in ("/rates", "/business-rates"):
        return 100                                   # the master rate sheets
    if path.startswith(("/personal", "/business/")) and "/resources/" not in path:
        return 80                                    # official product pages
    if path in ("", "/contact", "/membership", "/about") or path.startswith("/about"):
        return 70                                    # core company pages
    if path.startswith("/calculators") or "calculator" in path:
        return 35                                    # calculators are often never updated
    if path.startswith("/newsroom") or re.match(r"^/(19|20)\d\d/", path):
        return 20                                    # press releases / blog posts age badly
    if path.startswith("/learn") or "/resources/" in path:
        return 15
    if path.startswith("/hubfs"):
        return 10                                    # PDFs and files
    return 50                                        # landing pages, promos, misc


_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _cells(line: str) -> list:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def parse_tables(text: str) -> list:
    lines = text.split("\n")
    out, i, last_text = [], 0, []
    while i < len(lines):
        ln = lines[i]
        if ln.lstrip().startswith("|") and i + 1 < len(lines) and _SEP.match(lines[i + 1]):
            header = _cells(ln)
            j, rows = i + 2, []
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                cells = _cells(lines[j])
                cells += [""] * (len(header) - len(cells))
                rows.append(dict(zip(header, cells)))
                j += 1
            heading = last_text[-1] if last_text else ""
            out.append(Table(heading=heading, header=header, rows=rows,
                             context=" / ".join(last_text[-3:])))
            i = j
            continue
        if ln.strip():
            last_text.append(ln.strip().lstrip("#").strip()[:120])
        i += 1
    return out


class Store:
    def __init__(self):
        self.versions = {}      # url -> [PageVersion, ...] oldest first
        self.snapshots = []     # [(snapshot_id, taken_on)]

    def add_snapshot(self, snapshot) -> None:
        self.snapshots.append((snapshot.snapshot_id, snapshot.taken_on))
        for p in snapshot.pages:
            text = clean(p.markdown)
            fetched = (p.fetched_at or "")[:10]
            pv = PageVersion(
                url=p.url, snapshot_id=snapshot.snapshot_id, taken_on=snapshot.taken_on,
                fetched_at=p.fetched_at or "", title=p.title or "", text=text,
                authority=authority(p.url),
                carried_forward=bool(fetched) and fetched < snapshot.taken_on,
                tables=parse_tables(text),
            )
            self.versions.setdefault(p.url, []).append(pv)

    def latest(self):
        """Newest version of each page."""
        return {u: v[-1] for u, v in self.versions.items()}

    def as_of(self, date: Optional[str]):
        """Each page as it stood on `date` (newest version taken on/before that day)."""
        if not date:
            return self.latest()
        out = {}
        for u, vs in self.versions.items():
            ok = [v for v in vs if v.taken_on <= date]
            if ok:
                out[u] = ok[-1]
        return out
