"""Step 1: versioned store + table parsing. answer() is still the naive paragraph match
(over the store's newest pages) so the scorer keeps running while we build the real thing."""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(next(d / "harness" for d in HERE.parents if (d / "harness" / "contract.py").exists())))
from contract import Answer, Conflict, Snapshot, Source  # noqa: E402
from store import Store  # noqa: E402

WORD = re.compile(r"[a-z0-9$%.]+")


class KnowledgeSystem:
    def __init__(self):
        self.store = Store()

    def ingest(self, snapshot: Snapshot) -> None:
        self.store.add_snapshot(snapshot)

    def answer(self, question, as_of=None):
        q = set(WORD.findall(question.lower()))
        best, best_score = None, 0
        for url, pv in self.store.as_of(as_of).items():
            for para in pv.text.split("\n\n"):
                s = len(q & set(WORD.findall(para.lower())))
                if s > best_score:
                    best, best_score = (url, pv.snapshot_id, para.strip()), s
        if not best:
            return Answer(text="I don't know.", confident=False)
        url, sid, para = best
        return Answer(text=para[:600], sources=[Source(url=url, snapshot_id=sid)])

    def conflicts(self):
        return []


def build():
    return KnowledgeSystem()
