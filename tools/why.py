"""python tools/why.py 'your question' [as_of] [--find 'text']  -> top-scoring chunks; --find shows where chunks containing the text rank."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "solution")); sys.path.insert(0, str(ROOT / "harness"))
import inspect_store
from solution import KnowledgeSystem
import engine, index

st = inspect_store.load()
ks = KnowledgeSystem()
for sid in sorted(st.snapshots):
    pass

from contract import Page, Snapshot
import json
sys.stdout.reconfigure(encoding="utf-8")
for d in sorted((ROOT / "snapshots").glob("0*/")):
    m = json.load(open(d / "manifest.json", encoding="utf-8"))
    pages = [Page(url=p["url"], title=p["title"], markdown=(d / p["file"]).read_text(encoding="utf-8"), fetched_at=p["fetched_at"]) for p in m["pages"]]
    ks.ingest(Snapshot(snapshot_id=m["snapshot_id"], taken_on=m["taken_on"], pages=pages))
args = sys.argv[1:]
find = None
page = None
if "--page" in args:
    i = args.index("--page"); page = args[i + 1]; del args[i:i + 2]
if "--find" in args:
    i = args.index("--find"); find = args[i + 1]; del args[i:i + 2]
q = args[0]
as_of = args[1] if len(args) > 1 else None
idx = ks._targets(as_of)[0]
groups = engine.query_groups(q)
print("groups:", [sorted(g) for g in groups], "| evidence needed:", [r.pattern[:40] for r in engine.required_evidence(q)])
scored, wts = engine.score_chunks(idx, groups, index.parse_quals(q), q)
for s, cov, c in scored[:8]:
    print(f"{s:.2f} cov={cov:.2f} {c.kind} auth={c.authority} pub={c.pub or '-'} {c.url.split('.com')[-1][:50]}\n     {c.text[:150]!r}")
if find:
    print(f"--- chunks containing {find!r}:")
    for rank, (s_, cov, c) in enumerate(scored):
        if find.lower() in c.text.lower():
            print(f"rank {rank} score={s_:.2f} cov={cov:.2f} auth={c.authority} pub={c.pub or '-'} toks={len(c.toks)} {c.url.split('.com')[-1][:55]}")
if page:
    for url, chunks in idx.page_text.items():
        if page in url:
            print(f"--- chunks of {url.split('.com')[-1]}")
            for i, t in enumerate(chunks[:12]):
                print(f"  {i} ({len(t)} chars) {t[:120]!r}")
print("ANSWER:", ks.answer(q, as_of).text[:200])