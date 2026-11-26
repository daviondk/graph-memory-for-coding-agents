"""Bounded winner cache and exact index fallback for transactional top-k packets."""
from collections import Counter
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "cutoff"))
from cutoff_store import CutoffStore
from core import M, NOW, Store


def key(pair):
    cid, score = pair
    return score, -cid


def refresh(pairs, capacity):
    cached = tuple(pairs)
    outside = key(cached[-1]) if len(cached) == capacity else None
    return cached, outside


def advance(state, changed, capacity, required):
    """None signals fallback. A None score means the object disappears."""
    cached, outside = state
    pool = dict(cached)
    for cid, score in changed.items():
        if score is None:
            pool.pop(cid, None)
        else:
            pool[cid] = score
    ordered = sorted(pool.items(), key=key, reverse=True)
    if len(ordered) > capacity:
        best_removed = key(ordered[capacity])
        outside = best_removed if outside is None else max(best_removed, outside)
    keep = tuple(ordered[:capacity])
    if outside is not None and (len(keep) < required or key(keep[required-1]) < outside):
        return None
    return keep, outside


class ReserveStore(Store):
    def __init__(self, db, capacity, mode, create=True):
        super().__init__(db, "snapshot", create)
        assert mode in ("lazy","eager") and capacity >= M
        self.capacity = capacity
        self.mode = mode
        self.event = None

    def fetch(self, q, phase):
        found = self.db.execute(NOW, (q,self.capacity)).fetchall()
        self.event[phase+"_probes"] += 1
        self.event[phase+"_rows"] += len(found)
        return refresh(found, self.capacity)

    def update(self, q, row, fault=False):
        c = self.db
        t = row["t"]
        self.event = Counter()
        c.execute("BEGIN IMMEDIATE")
        try:
            head = c.execute("SELECT rev FROM head WHERE q=?", (q,)).fetchone()
            rev = head[0] if head else 0
            if t <= rev:
                if c.execute("SELECT digest FROM receipt WHERE q=? AND rev=?", (q,t)).fetchone() != (row["sha"],):
                    raise ValueError("conflicting replay")
                c.commit()
                return False
            if t != rev + 1:
                raise ValueError("version gap")
            prior = self.last.get(q)
            state = prior[1] if prior and prior[0] == rev else self.fetch(q, "cold")
            old = list(state[0][:M])
            dirty = {}
            for cid in row["born"]:
                c.execute("INSERT INTO source VALUES(?,?,?,0)", (q,cid,t))
                dirty[cid] = 0
            net = Counter()
            for a,b,d in row["delta"]:
                address = (q,a,b)
                prev = c.execute("SELECT weight FROM edge WHERE q=? AND src=? AND dst=? AND end IS NULL", address).fetchone()
                new = (prev[0] if prev else 0) + d
                eligible = c.execute("SELECT count(*) FROM source WHERE q=? AND cid IN (?,?)", (q,a,b)).fetchone()[0]
                if d == 0 or new < 0 or eligible != len({a,b}):
                    raise ValueError("invalid edge")
                if prev:
                    c.execute("UPDATE edge SET end=? WHERE q=? AND src=? AND dst=? AND end IS NULL", (t,*address))
                if new:
                    c.execute("INSERT INTO edge VALUES(?,?,?,?,NULL,?)", (*address,t,new))
                net[a] += d
            for cid,v in net.items():
                if v:
                    dirty[cid] = c.execute("UPDATE source SET score=score+? WHERE q=? AND cid=? RETURNING score", (v,q,cid)).fetchone()[0]
                    self.event["score_rows"] += 1
            target = M if self.mode == "lazy" else self.capacity
            next_state = advance(state, dirty, self.capacity, target)
            if next_state is None:
                next_state = self.fetch(q, "warm")
            packet = list(next_state[0][:M])
            self._maintain(q, t, old, packet, row["born"], net)
            if fault:
                raise RuntimeError("test rollback")
            c.execute("INSERT INTO receipt VALUES(?,?,?)", (q,t,row["sha"]))
            c.execute("INSERT INTO head VALUES(?,?) ON CONFLICT(q) DO UPDATE SET rev=excluded.rev", (q,t))
            c.commit()
            self.last[q] = (t, next_state)
            self.event["pairs"] = len(next_state[0])
            self.event["has_bound"] = int(next_state[1] is not None)
            return True
        except BaseException:
            c.rollback()
            raise


class InstrumentedCutoff(CutoffStore):
    """Previous implementation unchanged; instrument its two ordered query sites."""
    def update(self, q, row, fault=False):
        self.event = Counter()
        rev = self.last.get(q, (None,))[0]
        self.cold_pending = rev != row["t"]-1
        def trace(statement):
            if " RETURNING SCORE" in statement.upper():
                self.event["score_rows"] += 1
        self.db.set_trace_callback(trace)
        try:
            changed = super().update(q, row, fault)
        finally:
            self.db.set_trace_callback(None)
        if changed:
            self.event["pairs"] = len(self.last[q][1])
        return changed

    def _top(self, q, k):
        pairs = super()._top(q,k)
        phase = "cold" if self.cold_pending else "warm"
        self.cold_pending = False
        self.event[phase+"_probes"] += 1
        self.event[phase+"_rows"] += len(pairs)
        return pairs

