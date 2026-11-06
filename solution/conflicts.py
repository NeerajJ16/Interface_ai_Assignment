"""Find places where the website contradicts itself, pick the winner, and say why."""
from __future__ import annotations

import re
from collections import OrderedDict, defaultdict

from contract import Conflict, Source
from index import TIER, fact_key

PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
BRANCH_CLAIM = re.compile(r"\b(\d{2})\s+branch office locations", re.I)

def _nums(metrics: str):
    out = OrderedDict()
    for m in PCT.finditer(metrics):
        out.setdefault(round(float(m.group(1)), 4), m.group(0).replace(" ", ""))
    return out

_INDEXES = []

def _audience(c) -> str:
    return "biz" if "/business" in c.url or "business" in c.heading.lower() else "per"

def _fact_key(c, tier: bool = True):
    return fact_key(c, _INDEXES[c.snap].bands.get(c.table_id, {}), tier)

def _best(obs):
    return max(obs, key=lambda o: (o[1].authority, not o[1].carried, o[1].url))

def row_conflicts(indexes):
    _INDEXES[:] = indexes
    obs = defaultdict(list)
    for i, idx in enumerate(indexes):
        for c in idx.chunks:
            if c.kind == "row" and c.metrics:
                n = _nums(c.metrics)
                if n:
                    obs[_fact_key(c)].append((i, c, n))

    rows = []
    for key, items in obs.items():
        sizes = defaultdict(int)
        for _, _, n in items:
            sizes[len(n)] += 1
        keep = max(sizes, key=sizes.get)
        items = [o for o in items if len(o[2]) == keep]
        last = max(i for i, _, _ in items)
        latest = [o for o in items if o[0] == last]
        per_url = defaultdict(set)
        for _, c, n in latest:
            per_url[c.url].add(tuple(n))
        if any(len(v) > 1 for v in per_url.values()):
            continue
        stale_copy = len({tuple(n) for _, _, n in latest}) > 1

        series = []
        for i in sorted({i for i, _, _ in items}):
            official = [o for o in items if o[0] == i and o[1].authority >= 80]
            if official:
                series.append((i, _best(official)))
        moved = len({tuple(o[2]) for _, o in series}) > 1
        if not (stale_copy or moved):
            continue

        win = _best(latest)
        values = OrderedDict()
        srcs = OrderedDict()
        for i, c, n in sorted(items, key=lambda o: o[0]) if moved else sorted(latest, key=lambda o: o[0]):
            if moved and c.authority < 80 and not stale_copy:
                continue
            for v, shown in n.items():
                values.setdefault(v, shown)
                srcs.setdefault(v, (c, indexes[i].snap_id))
        rows.append(dict(key=key, win=win, values=values, srcs=srcs, stale=stale_copy, moved=moved,
                         latest=latest, last=last))

    groups = OrderedDict()
    for r in rows:
        c = r["win"][1]
        groups.setdefault(_fact_key(c, tier=False), []).append(r)

    out = []
    for key, rs in groups.items():
        c0 = rs[0]["win"][1]
        lab = TIER.sub("", c0.label).strip(" ,:-")
        topic = f"{lab} ({c0.heading})" if lab else c0.heading
        if _audience(c0) == "biz" and "business" not in topic.lower():
            topic += " [business]"
        vals, srcs, res = OrderedDict(), OrderedDict(), OrderedDict()
        for r in rs:
            for v, shown in r["values"].items():
                vals.setdefault(v, shown)
                srcs.setdefault(v, r["srcs"][v])
            for v, shown in r["win"][2].items():
                res.setdefault(v, shown)
        stale = any(r["stale"] for r in rs)
        moved = any(r["moved"] for r in rs)
        win_c = rs[0]["win"][1]
        last_id = indexes[rs[0]["last"]].snap_id
        wrong = sorted({o[1].url.split("dupaco.com")[-1] or "/" for r in rs for o in r["latest"]
                        if tuple(o[2]) != tuple(r["win"][2]) and o[1].authority < win_c.authority})
        why = []
        if stale and wrong:
            why.append(f"{win_c.url.split('dupaco.com')[-1]} is the official, most authoritative page; "
                       f"{', '.join(wrong[:4])} still show older values")
        elif stale:
            why.append("pages disagree; the highest-authority, freshest page was chosen")
        if moved:
            why.append(f"the official value changed between snapshots; the newest ({last_id}) is current")
        out.append(Conflict(
            topic=topic,
            values=list(vals.values()),
            sources=[Source(url=c.url, snapshot_id=sid, quote=c.metrics[:100]) for c, sid in srcs.values()][:8],
            resolution=", ".join(res.values()),
            reason="; ".join(why),
        ))
    return out

def claim_conflicts(indexes):
    """Boilerplate counts that drift between press releases (e.g. '22 branch office locations')."""
    latest = indexes[-1]
    seen = []
    for c in latest.chunks:
        if c.kind == "text" and c.pub:
            m = BRANCH_CLAIM.search(c.text)
            if m:
                seen.append((c.pub, m.group(1), c.url))
    if len({n for _, n, _ in seen}) < 2:
        return []
    seen.sort()
    newest = seen[-1]
    values, srcs = OrderedDict(), OrderedDict()
    for pub, n, url in seen:
        values.setdefault(n, f"{n} branch office locations")
        srcs[n] = (url, pub)
    return [Conflict(
        topic="Number of Dupaco branch office locations",
        values=list(values.values()),
        sources=[Source(url=u, snapshot_id=latest.snap_id, quote=f"{n} branch office locations ({p})") for n, (u, p) in srcs.items()],
        resolution=f"{newest[1]} branch office locations",
        reason=f"press-release boilerplate drifts over time; the most recent release ({newest[0]}) says {newest[1]}",
    )]

def build_conflicts(indexes):
    return row_conflicts(indexes) + claim_conflicts(indexes)