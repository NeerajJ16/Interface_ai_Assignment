"""python tools/show_conflicts.py  -> builds the system and prints every conflict we report."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "solution")); sys.path.insert(0, str(ROOT / "harness"))
from contract import Page, Snapshot
sys.stdout.reconfigure(encoding="utf-8")
from solution import KnowledgeSystem
ks = KnowledgeSystem()
for d in sorted((ROOT / "snapshots").glob("0*/")):
    m = json.load(open(d / "manifest.json", encoding="utf-8"))
    ks.ingest(Snapshot(snapshot_id=m["snapshot_id"], taken_on=m["taken_on"], pages=[
        Page(url=p["url"], title=p["title"], markdown=(d / p["file"]).read_text(encoding="utf-8"), fetched_at=p["fetched_at"]) for p in m["pages"]]))
cs = ks.conflicts()
print(len(cs), "conflicts")
for c in cs:
    print(f"\n* {c.topic}\n  values: {c.values}\n  resolution: {c.resolution}\n  why: {c.reason}")