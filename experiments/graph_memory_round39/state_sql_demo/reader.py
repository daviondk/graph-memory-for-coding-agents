"""Offline SQLite state reader. No evaluator database is opened by the ranker."""
from pathlib import Path
import gzip
import json
import math
import sqlite3
import struct

D = Path(__file__).resolve().parent
TOP = "SELECT unit FROM unit WHERE state=? ORDER BY score DESC,unit LIMIT ?"
BGE = "SELECT unit FROM unit WHERE state=? ORDER BY bge_rank,unit LIMIT ?"
FRESH = """SELECT unit FROM unit WHERE state=?
           ORDER BY tree_score(features,seen) DESC,unit LIMIT ?"""


def load_model():
    m = json.loads(gzip.decompress((D/"model.json.gz").read_bytes()))
    return Ensemble(m)


class Ensemble:
    def __init__(self, params):
        self.params = params
        self.trees = [list(zip(t["is_leaf"], t["value"], t["feature_idx"], t["num_threshold"],
                               t["left"], t["right"], t["missing_go_to_left"])) for t in params["trees"]]
        self.unpack = struct.Struct("<" + str(params["width"]) + "f").unpack
        self.calls = 0

    def value(self, packed, seen):
        self.calls += 1
        x = self.unpack(packed)
        total = self.params["base"]
        for tree in self.trees:
            idx = 0
            while True:
                leaf, value, feature, threshold, left, right, nan_left = tree[idx]
                if leaf:
                    total += value
                    break
                v = seen if feature == 11 else x[feature]
                idx = left if v <= threshold or (math.isnan(v) and nan_left) else right
        return total


class Reader:
    def __init__(self):
        uri = (D/"reader.sqlite").as_uri() + "?mode=ro"
        source = sqlite3.connect(uri, uri=True)
        self.db = sqlite3.connect(":memory:")
        source.backup(self.db)
        source.close()
        self.model = load_model()
        self.db.create_function("tree_score", 2, self.model.value, deterministic=True)

    def top(self, state, k=8, mode="indexed"):
        sql = {"indexed": TOP, "fresh": FRESH, "bge": BGE}[mode]
        return [r[0] for r in self.db.execute(sql, (state, k))]

    def set_seen(self, state, unit, seen, fresh=False):
        if seen not in (0, 1):
            raise ValueError("seen must be 0 or 1")
        with self.db:
            if fresh:
                sql, args = "UPDATE unit SET seen=? WHERE state=? AND unit=?", (seen, state, unit)
            else:
                sql, args = "UPDATE unit SET seen=?, score=tree_score(features,?) WHERE state=? AND unit=?", (seen, seen, state, unit)
            if not self.db.execute(sql, args).rowcount:
                raise ValueError("unknown state or unit")
            top = self.top(state, mode="fresh" if fresh else "indexed")
        return top

    def reset(self, state):
        with self.db:
            self.db.execute("UPDATE unit SET seen=base_seen,score=base_score WHERE state=?", (state,))

    def states(self):
        return [s for s, in self.db.execute("SELECT state FROM state ORDER BY state")]

    def units(self, state):
        return [dict(unit=u, file=f, start=a, end=b, tokens=t, seen=s, base_seen=s0,
                     score=v, base_score=v0, bge_rank=rank) for u,f,a,b,t,s,s0,v,v0,rank in self.db.execute(
            """SELECT unit,file,line_start,line_end,tokens,seen,base_seen,score,base_score,bge_rank
               FROM unit WHERE state=? ORDER BY unit""", (state,))]


class Grader:
    def __init__(self):
        self.db = sqlite3.connect((D/"grader.sqlite").as_uri()+"?mode=ro", uri=True)

    def evaluate(self, state, top, k):
        if not self.db.execute("SELECT 1 FROM evaluation_state WHERE state=?", (state,)).fetchone():
            raise ValueError("unknown state")
        chosen = set(top[:k])
        groups = []
        for group, quota in self.db.execute("SELECT gid,quota FROM required WHERE state=? ORDER BY gid", (state,)):
            members = {u for u, in self.db.execute("SELECT unit FROM acceptable WHERE state=? AND gid=?", (state,group))}
            groups.append(dict(group=group, have=len(members & chosen), need=quota, hits=sorted(members & chosen)))
        alt = {}
        for route, u in self.db.execute("SELECT route,unit FROM alternative WHERE state=?", (state,)):
            alt.setdefault(route,set()).add(u)
        routes = [i for i, us in sorted(alt.items()) if us <= chosen]
        complete = all(g["have"] >= g["need"] for g in groups) or bool(routes)
        return dict(complete=int(complete), groups=groups, complete_alternatives=routes)
