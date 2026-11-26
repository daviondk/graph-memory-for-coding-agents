"""Live metadata-only packet selection; portable standard-library SQLite and exact DP."""
from collections import defaultdict
from pathlib import Path
import sqlite3

D=Path(__file__).resolve().parent
BUDGETS=(1024,2048,3072)

def open_readonly(path):
    return sqlite3.connect(path.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)

def choose_tail(rows,capacity):
    candidates=[r for r in rows if r[2]<=capacity]; best=[0.0]*(capacity+1);trace=[]
    for _,_,cost,gain in candidates:
        selected=bytearray(capacity+1)
        for limit in range(capacity,cost-1,-1):
            value=best[limit-cost]+gain
            if value>best[limit]:best[limit]=value;selected[limit]=1
        trace.append(selected)
    chosen=[]
    for row,flags in zip(reversed(candidates),reversed(trace)):
        if flags[capacity]:chosen.append(row);capacity-=row[2]
    return list(reversed(chosen))

class Reader:
    def __init__(self,path=D/"reader.sqlite"):
        self.db=open_readonly(path)
    def queries(self):
        return [q for q, in self.db.execute("SELECT q FROM query ORDER BY q")]
    def sources(self,q):
        return [dict(id=s,role=r,position=p,length=n,candidates=c) for s,r,p,n,c in self.db.execute("""SELECT o.source,o.role,o.position,o.length,count(DISTINCT s.id) FROM origin o JOIN span s ON s.q=o.q AND s.source=o.source WHERE o.q=? GROUP BY o.source ORDER BY count(DISTINCT s.id) DESC,o.source""",(q,))]
    def choose(self,q,budget,exclude=None):
        if budget not in BUDGETS:raise ValueError("unsupported budget")
        if exclude is not None and not self.db.execute("SELECT 1 FROM origin WHERE q=? AND source=?",(q,exclude)).fetchone():raise ValueError("unknown source")
        sql="SELECT id,rank,tokens,utility FROM node n WHERE q=?"
        args=(q,)
        if exclude is not None:
            sql+=" AND NOT EXISTS (SELECT 1 FROM span s WHERE s.q=n.q AND s.id=n.id AND s.source=?)";args=(q,exclude)
        rows=self.db.execute(sql+" ORDER BY rank",args).fetchall()
        if not rows and not self.db.execute("SELECT 1 FROM query WHERE q=?",(q,)).fetchone():raise ValueError("unknown query")
        head=[];cost=0; threshold=budget//2
        for row in rows:
            if cost+row[2]>threshold:break
            head.append(row);cost+=row[2]
        tail=choose_tail(rows[len(head):],budget-cost)
        return dict(query=q,budget=budget,threshold=threshold,exclude=exclude,eligible=len(rows),tokens=cost+sum(r[2] for r in tail),head=[r[0] for r in head],tail=[r[0] for r in tail],ids=[r[0] for r in head+tail])
    def explain(self,result):
        q=result['query']; head=set(result['head']);items=[]
        for i in result['ids']:
            hashed,role,rank,cost,u=self.db.execute("SELECT node_hash,role,rank,tokens,utility FROM node WHERE q=? AND id=?",(q,i)).fetchone()
            spans=[dict(source=s,start=a,end=b,position=p,role=r) for s,a,b,p,r in self.db.execute("SELECT s.source,s.lo,s.hi,o.position,o.role FROM span s JOIN origin o ON o.q=s.q AND o.source=s.source WHERE s.q=? AND s.id=? ORDER BY s.source,s.lo",(q,i))]
            edges=[dict(direction=d,relation=r,node=n) for d,r,n in self.db.execute("""SELECT 'in',relation,left_node FROM edge WHERE q=? AND right_node=? UNION ALL SELECT 'out',relation,right_node FROM edge WHERE q=? AND left_node=? ORDER BY 1,2,3""",(q,hashed,q,hashed))]
            items.append(dict(id=i,hash=hashed,role=role,rank=rank+1,tokens=cost,utility=u,reason="prefix" if i in head else "knapsack",spans=spans,edges=edges))
        return items

def merged(intervals):
    out=[]
    for a,b in sorted(intervals):
        if out and a<=out[-1][1]:out[-1][1]=max(b,out[-1][1])
        else:out.append([a,b])
    return out

class Evaluator:
    def __init__(self,path=D/"grader.sqlite"):
        self.db=open_readonly(path)
    def evaluate(self,reader,result):
        q=result['query'];truth=defaultdict(list);seen=defaultdict(list)
        for s,a,b in self.db.execute("SELECT source,lo,hi FROM gold WHERE q=?",(q,)):truth[s].append((a,b))
        if not truth:raise ValueError("unknown evaluation query")
        for i in result['ids']:
            for s,a,b in reader.db.execute("SELECT source,lo,hi FROM span WHERE q=? AND id=?",(q,i)):seen[s].append((a,b))
        length=covered=0
        for source,intervals in truth.items():
            target=merged(intervals);selected=merged(seen[source]);length+=sum(b-a for a,b in target)
            covered+=sum(max(0,min(b,d)-max(a,c)) for a,b in target for c,d in selected)
        return dict(full_support=int(length==covered),coverage=covered/length,covered_chars=covered,gold_chars=length)
