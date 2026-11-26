"""An exact invalidation certificate for source exclusions over a frozen utility graph."""
import importlib.util
import json
from pathlib import Path
import sqlite3
from time import perf_counter_ns
import numpy as np

D=Path(__file__).resolve().parent
DEMO=D.parent/"provenance_packet_demo"
shared=D.parent/"remaining_budget/reader.py"
spec=importlib.util.spec_from_file_location("residual_picker",shared)
picker=importlib.util.module_from_spec(spec);spec.loader.exec_module(picker)
BUDGET=2048

def selection(rows,budget,solve):
    ids=np.asarray([r[0] for r in rows],dtype=int)
    costs=np.asarray([r[1] for r in rows],dtype=np.int32)
    utility=np.asarray([r[2] for r in rows],dtype=float)
    cumulative=costs.cumsum()
    count=int(cumulative.searchsorted(budget//2,side="right"))
    cap=budget-(int(cumulative[count-1]) if count else 0)
    feasible=np.flatnonzero(costs[count:]<=cap)+count
    tail=feasible[solve(costs[feasible],utility[feasible],cap)]
    packet=tuple(int(n) for n in np.r_[ids[:count],ids[tail]])
    barrier=int(ids[count]) if count<len(ids) else None
    return packet,barrier

class Snapshot:
    def __init__(self,path):
        self.conn=sqlite3.connect(path.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
        self.conn.executescript("""
            CREATE TEMP TABLE packet(q TEXT PRIMARY KEY,ids TEXT NOT NULL,barrier INTEGER);
            CREATE TEMP TABLE dependency(q TEXT,source TEXT,selected INTEGER,barrier INTEGER,
                PRIMARY KEY(q,source)) WITHOUT ROWID;
        """)
        self.solve=picker.kernel()

    def rows(self,q,source):
        if source is None:
            return self.conn.execute("SELECT id,tokens,utility FROM node WHERE q=? ORDER BY rank",(q,)).fetchall()
        return self.conn.execute("""SELECT id,tokens,utility FROM node n WHERE q=? AND NOT EXISTS
            (SELECT 1 FROM span s WHERE s.q=n.q AND s.id=n.id AND s.source=?) ORDER BY rank""",(q,source)).fetchall()

    def full(self,q,source):
        return selection(self.rows(q,source),BUDGET,self.solve)[0]

    def prepare(self,q):
        begin=perf_counter_ns()
        packet,barrier=selection(self.rows(q,None),BUDGET,self.solve)
        selected=set(packet);mid=perf_counter_ns()
        self.conn.execute("INSERT INTO packet VALUES (?,?,?)",(q,json.dumps(packet,separators=(",",":")),barrier))
        flags={}
        for unit,src in self.conn.execute("SELECT DISTINCT id,source FROM span WHERE q=?",(q,)):
            if unit in selected or unit==barrier:
                item=flags.setdefault(src,[0,0]);item[0]|=int(unit in selected);item[1]|=int(unit==barrier)
        self.conn.executemany("INSERT INTO dependency VALUES (?,?,?,?)",[(q,s,*v) for s,v in flags.items()])
        self.conn.commit()
        return packet,barrier,mid-begin,perf_counter_ns()-mid

    def result(self,q,source,mode):
        if mode=="full":return self.full(q,source),True
        cur=self.conn.execute("""SELECT p.ids,p.barrier,coalesce(d.selected,0),coalesce(d.barrier,0)
            FROM packet p LEFT JOIN dependency d ON p.q=d.q AND d.source=? WHERE p.q=?""",(source,q)).fetchone()
        packed,boundary,selected,boundary_affected=cur
        dirty=bool(selected)
        if mode=="certificate":dirty=dirty or bool(boundary_affected)
        elif mode=="late_boundary":
            if not dirty and boundary is not None:
                dirty=bool(self.conn.execute("SELECT 1 FROM span WHERE q=? AND id=? AND source=? LIMIT 1",(q,boundary,source)).fetchone())
        elif mode!="selected_only":raise ValueError(mode)
        return (self.full(q,source),True) if dirty else (tuple(json.loads(packed)),False)

