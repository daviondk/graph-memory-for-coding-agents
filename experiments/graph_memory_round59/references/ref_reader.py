"""Load certified immutable source rows when a query first reaches a selected event."""
from collections import Counter
from packet import decode, unpack
from checkpoint import Pinned, best


class ReferenceReader(Pinned):
    def __init__(self,path,mode):
        super().__init__(path,False)
        self.selected=frozenset()
        self.source_calls=self.source_bytes=0
        self.mode=mode
        if mode!="cold":
            self.open_snapshot()

    def fetch(self, addresses):
        result=[]
        ordered=sorted(addresses)
        for pos in range(0,len(ordered),400):
            chunk=ordered[pos:pos+400]
            placeholders=",".join("?" for _ in chunk)
            rows=self.db.execute("SELECT members FROM event WHERE j IN ("+placeholders+") ORDER BY j",chunk)
            blobs=[r[0] for r in rows]
            if len(blobs)!=len(chunk):raise ValueError("referenced source rows unavailable")
            result.extend(zip(chunk,blobs))
        return result,(len(ordered)+399)//400

    def keep(self,j,ids):
        self.pinned[j]=ids
        for f in ids:self.pinned_for[f].add(j)

    def open_snapshot(self):
        self.open_calls+=1
        if not self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='snapshot'").fetchone():return
        self.open_calls+=1
        row=self.db.execute("SELECT v FROM snapshot WHERE k=1").fetchone()
        if not row:return
        blob=row[0]
        self.loaded_bytes=len(blob)
        self.open_calls+=1
        row=self.db.execute("SELECT rev FROM event WHERE j=?",(self.fence-1,)).fetchone()
        sha=row[0] if row else b""
        self.receipt_bytes=len(sha)
        try:
            selected,bodies=decode(blob,self.fence,sha)
            if self.mode=="eager":
                rows,self.source_calls=self.fetch(selected)
                self.source_bytes=sum(len(data) for _,data in rows)
                bodies={j:unpack(data) for j,data in rows}
        except ValueError:
            self.rejected=True
            return
        self.selected=selected
        for j,ids in bodies.items():self.keep(j,ids)

    def read(self,f,tie,prior):
        pinned=self.pinned_for.get(f,())
        hot=self.hot.incident.get(f,())
        counts=Counter()
        for j in pinned:counts.update(self.pinned[j])
        for j in hot:counts.update(self.hot.live[j])
        if f in self.complete and f not in self.hot.lost_shared:
            return best(counts,f,tie,prior),(0,0,0,0,0,0)
        row=self.db.execute("SELECT js FROM posting WHERE f=?",(f,)).fetchone()
        if not row:
            self.complete.add(f)
            return best(counts,f,tie,prior),(1,0,0,0,0,0)
        ids=unpack(row[0])
        missing=[j for j in ids if j not in pinned and j not in hot]
        rows,calls=self.fetch(missing)
        total=new=0
        for j,blob in rows:
            body=unpack(blob)
            total+=len(blob)
            counts.update(body)
            if j in self.selected:
                self.keep(j,body)
                new+=len(blob)
        if all(j>=self.fence or j in self.selected for j in ids):self.complete.add(f)
        return best(counts,f,tie,prior),(1,len(row[0]),calls,total,new,len(rows))
