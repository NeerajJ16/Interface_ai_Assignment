"""python tools/show_misses.py  -> prints each practice question below full score, with our answer."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
res = [json.loads(l) for l in (ROOT / "results" / "per_question.jsonl").read_text().splitlines()]
ev = {json.loads(l)["id"]: json.loads(l) for l in (ROOT / "eval" / "public_eval.jsonl").read_text().splitlines()}
for r in res:
    if r["score"] < 0.99:
        e = ev[r["id"]]
        print(f"\n{r['id']} [{r['category']}] score={r['score']} missed={r['missed']} trap={r['trap_hits']}")
        print("  Q:", e["question"])
        a = r.get("answer") or {}
        a = a.get("text", "") if isinstance(a, dict) else str(a)
        print("  A:", a[:300].replace("\n", " || "))