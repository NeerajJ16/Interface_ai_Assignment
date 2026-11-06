"""Knowledge system: versioned snapshots -> chunk index per snapshot -> qualifier-aware answers."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(next(d / "harness" for d in HERE.parents if (d / "harness" / "contract.py").exists())))
from contract import Answer, Conflict, Snapshot, Source  
from engine import REFUSAL, attempt  
from index import SnapshotIndex, row_chunk, text_chunks  
from store import Store  


class KnowledgeSystem:
    def __init__(self):
        self.store = Store()
        self.indexes = []        

    def ingest(self, snapshot: Snapshot) -> None:
        self.store.add_snapshot(snapshot)
        si = len(self.indexes)
        idx = SnapshotIndex(snapshot.snapshot_id, snapshot.taken_on)
        for url, versions in self.store.versions.items():
            pv = versions[-1]
            if pv.snapshot_id != snapshot.snapshot_id:
                continue
            idx.chunks.extend(text_chunks(pv, si))
            for ti, t in enumerate(pv.tables):
                for ri, row in enumerate(t.rows):
                    idx.chunks.append(row_chunk(pv, si, t, ti, ri, row))
        idx.finalize()
        self.indexes.append(idx)

    def _targets(self, as_of):
        """Snapshots to search, best first: newest on/before as_of, then progressively older."""
        idxs = [i for i in self.indexes if not as_of or i.taken_on <= as_of]
        return list(reversed(idxs))

    def answer(self, question, as_of=None):
        for idx in self._targets(as_of):
            res = attempt(idx, question)
            if res:
                text, urls, _ = res
                return Answer(text=text, sources=[Source(url=u, snapshot_id=idx.snap_id) for u in urls])
            break      
        return Answer(text=REFUSAL, confident=False)

    def conflicts(self):
        return []


def build():
    return KnowledgeSystem()