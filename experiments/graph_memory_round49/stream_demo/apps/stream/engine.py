"""A visitor's incremental DP and a separate exact calculator over read-only SQLite inputs."""
from bisect import bisect_left
from collections import defaultdict
from pathlib import Path
import json
import sqlite3

D = Path(__file__).resolve().parent
B, T = 2048, 1024

class History:
    def __init__(self, label):
        uri=(D/"observations.sqlite").as_uri()+"?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            rec=conn.execute("SELECT steps FROM history WHERE id=?", (label,)).fetchone()
            if not rec:
                raise ValueError("Unknown history")
            self.steps=rec[0]
            self.units=[(b,i,c,v,json.loads(o)) for b,i,c,v,o in conn.execute(
                "SELECT born,id,cost,utility,owners FROM unit WHERE history=? ORDER BY seq",(label,))]
            self.edits=defaultdict(list)
            for step,src,k in conn.execute("SELECT step,owner,count FROM witness WHERE history=? ORDER BY step,owner",(label,)):
                self.edits[step].append((src,k))

def verify_from_rows(history, step):
    balances=dict(change for s in range(1,step+1) for change in history.edits[s])
    available=[r for r in history.units if r[0]<=step]
    room=B
    ids=[]
    for _,ident,cost,_,_ in reversed(available):
        if room-cost<B-T:
            break
        room-=cost
        ids.append(ident)
    rotated=available[:len(available)-len(ids)]
    utility=[0]*(room+1)
    mask=[0]*(room+1)
    for j,(_,ident,price,base,owners) in enumerate(rotated):
        value=base+sum(min(4,balances.get(i,0))<<28 for i in owners)
        for w in range(room,price-1,-1):
            trial=utility[w-price]+value
            if trial>utility[w]:
                utility[w]=trial
                mask[w]=mask[w-price] | (1<<j)
    return ids+[r[1] for j,r in reversed(list(enumerate(rotated))) if (mask[room]>>j)&1]

class Reader:
    def __init__(self, history, spacing):
        self.history=history
        self.spacing=spacing
        self.step=0
        self.cut=0
        self.values=[]
        self.balance={}
        self.by_owner=defaultdict(list)
        self.prefix=[0]
        self.best=[0]*(B+1)
        self.snap={}
        self.choices=[]
        self.last={}
        self.visits=0
        self.direct=0

    def advance(self, target):
        if not self.step < target <= self.history.steps:
            raise ValueError("Next group outside the stream")
        units=self.history.units
        dirty=len(units)
        old_visible=len(self.values)
        change_count=0
        for t in range(self.step+1,target+1):
            i=len(self.values)
            while i<len(units) and units[i][0]==t:
                _,_,cost,base,owners=units[i]
                for owner in owners:
                    self.by_owner[owner].append(i)
                self.values.append(base+sum(min(4,self.balance.get(owner,0))<<28 for owner in owners))
                self.prefix.append(self.prefix[-1]+cost)
                i+=1
            for src,k in self.history.edits[t]:
                change_count+=1
                shift=(min(4,k)-min(4,self.balance.get(src,0)))<<28
                self.balance[src]=k
                if shift:
                    for index in self.by_owner[src]:
                        dirty=min(dirty,index)
                        self.values[index]+=shift
        cut=bisect_left(self.prefix,self.prefix[-1]-T)
        room=B-(self.prefix[-1]-self.prefix[cut])
        start=self.cut
        if dirty<start:
            start=(dirty//self.spacing)*self.spacing if self.spacing else 0
            self.best=self.snap[start].copy() if start else [0]*(B+1)
        rewound=self.cut-start
        for i in range(start,cut):
            cost=units[i][2]
            value=self.values[i]
            take=bytearray(B+1)
            for w in range(B,cost-1,-1):
                alt=self.best[w-cost]+value
                if alt>self.best[w]:
                    self.best[w]=alt
                    take[w]=1
            if i<len(self.choices):
                self.choices[i]=take
            else:
                self.choices.append(take)
            if self.spacing and (i+1)%self.spacing==0:
                self.snap[i+1]=self.best.copy()
        selected=[units[i][1] for i in range(len(self.values)-1,cut-1,-1)]
        for i in range(cut-1,-1,-1):
            if self.choices[i][room]:
                selected.append(units[i][1])
                room-=units[i][2]
        self.visits+=cut-start
        self.direct+=cut
        self.last=dict(step=target,total=self.history.steps,visible=len(self.values),new=len(self.values)-old_visible,
            changes=change_count,old_cut=self.cut,cut=cut,restored=start,rewound=rewound,rows=cut-start,full_rows=cut,
            cumulative=self.visits,full_cumulative=self.direct,tokens=B-room,ids=selected,checkpoints=len(self.snap))
        self.step=target
        self.cut=cut
        return self.last
