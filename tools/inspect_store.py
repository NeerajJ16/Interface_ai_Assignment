"""Debug helper: python tools/inspect_store.py <url-substring> [snapshot-substring]
Loads all snapshots and prints parsed tables for matching pages (run from kit root)."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "harness")); sys.path.insert(0, str(ROOT / "solution"))
from contract import Page, Snapshot
from store import Store

def load():
    st = Store()
    for d in sorted((ROOT / "snapshots").glob("0*/")):
        m = json.load(open(d / "manifest.json"))
        pages = [Page(url=p["url"], title=p["title"], markdown=(d / p["file"]).read_text(), fetched_at=p["fetched_at"]) for p in m["pages"]]
        st.add_snapshot(Snapshot(snapshot_id=m["snapshot_id"], taken_on=m["taken_on"], pages=pages))
    return st

if __name__ == "__main__":
    st = load()
    pat, snap = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "05_")
    for url, vs in st.versions.items():
        if pat in url:
            for v in vs:
                if snap in v.snapshot_id:
                    print(f"\n## {url} [{v.snapshot_id}] auth={v.authority} carried_forward={v.carried_forward} tables={len(v.tables)}")
                    for t in v.tables[:6]:
                        print(f"  - [{t.heading[:60]}] cols={t.header}")
                        for r in t.rows[:3]: print("      ", list(r.values()))
