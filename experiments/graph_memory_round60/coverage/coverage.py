"""Recover exact incidences as a union of resident events and explicitly charged exceptions."""
from collections import Counter,deque
from pathlib import Path
import sys

R59=Path(__file__).resolve().parents[2]/"graph_memory_round59"
sys.path.insert(0,str(R59/"reconcile"))
from summary_cache import full,expand,append as append_exact,SketchPolicy,XOR,NUM
from lazy_reader import Cache,Policy,Hot,EVENT,POST,varints,unpack,best

EXCEPTION=6


def prefix_number(blob):
    value=0
    for pos,c in enumerate(blob[1:],1):
        value|=(c&127)<<(7*(pos-1))
        if c<128:return value,pos+1
    raise ValueError("missing cardinality")


def pack_exceptions(number,excluded):
    return bytes([EXCEPTION])+varints((number,))+(full(tuple(sorted(excluded))) if excluded else b"")


def parts(blob):
    n,offset=prefix_number(blob)
    return n,(expand(blob[offset:]) if offset<len(blob) else ())


class WithEvictions(Cache):
    def __init__(self,limit):
        super().__init__(limit)
        self.pending=deque()
        self.pending_bytes=0
        self.peak_queued=0;self.peak_queue_bytes=0

    def drop(self,key):
        if key[0]==EVENT:
            blob=self.items[key]
            self.pending.append((key[1],blob))
            self.pending_bytes+=len(blob)
            self.peak_queued=max(self.peak_queued,len(self.pending))
            self.peak_queue_bytes=max(self.peak_queue_bytes,self.pending_bytes)
        super().drop(key)


def possible_losses(hot,files):
    # An event can lose its final owner only if it is now the oldest for an updated owner.
    candidates={}
    for f in files:
        queue=hot.owned.get(f)
        if queue is not None and len(queue)==8:
            j=queue[0]
            candidates[j]=hot.live[j]
    return candidates


class Coverage(Policy):
    def __init__(self,store,hot,cap,notify):
        super().__init__(store,hot,"joint",cap)
        self.notify=notify
        if notify:self.cache=WithEvictions(cap)
        self.resources=Counter()

    def unavailable(self,j,files):
        if j in self.hot.live or (EVENT,j) in self.cache.items:return
        self.resources["last_copy_lost"]+=1
        for f in files:
            key=(POST,f)
            record=self.cache.items.get(key)
            if record is None or record[0]!=EXCEPTION:continue
            n,exceptions=parts(record)
            self.resources["maintenance_packet_bytes_decoded"]+=len(record)
            if j not in exceptions:
                changed=pack_exceptions(n,(*exceptions,j))
                self.cache.put(key,changed,refresh=False)
                self.resources["exception_insertions"]+=1
                self.resources["maintenance_packet_bytes_encoded"]+=len(changed)

    def drain(self):
        if not self.notify:return
        steps=0
        while self.cache.pending:
            j,blob=self.cache.pending.popleft()
            self.cache.pending_bytes-=len(blob)
            steps+=1
            if j in self.hot.live or (EVENT,j) in self.cache.items:continue
            self.resources["maintenance_body_bytes"]+=len(blob)
            self.unavailable(j,unpack(blob))
        self.resources["max_queue_drain"]=max(self.resources["max_queue_drain"],steps)
        assert self.cache.pending_bytes==0

    def after_committed(self,j,files,hot_losses):
        for f in files:
            key=(POST,f);record=self.cache.items.get(key)
            if record is None:continue
            if record[0]==EXCEPTION:
                n,pos=prefix_number(record)
                updated=bytes([EXCEPTION])+varints((n+1,))+record[pos:]
            else:updated=append_exact(record,j)
            self.cache.put(key,updated,refresh=False)
            self.cache.updates+=1
            self.drain()
        if self.notify:
            for old,body in hot_losses:
                self.resources["hot_eviction_candidates_processed"]+=1
                self.unavailable(old,body)
                self.drain()

    def read(self,f,tie,prior,audit_ids=None):
        counts=Counter();stats=Counter()
        hot=self.hot.incident.get(f,())
        for j in hot:counts.update(self.hot.live[j])
        ids=None
        if not(f in self.known and f not in self.hot.lost_shared):
            record=self.cache.get((POST,f))
            if record is not None:
                if record[0]!=EXCEPTION:
                    ids=expand(record);stats["exact_hit"]+=1
                else:
                    n,ex=parts(record)
                    resident=set(hot)
                    for (kind,j),blob in self.cache.items.items():
                        if kind==EVENT:
                            stats["scan_objects"]+=1;stats["scan_bytes"]+=len(blob)
                            if f in unpack(blob):resident.add(j)
                    available=resident.union(ex)
                    if len(available)==n:
                        ids=tuple(sorted(available))
                        stats["certified"]+=1
                        needed=len(available-resident)
                        stats["covered_missing_ids"]+=needed
                        if needed>=2:stats["certified_multiple"]+=1
                    else:
                        assert len(available)<n
                        stats["guard_fallback"]+=1
            if ids is None:
                row=self.store.db.execute("SELECT js FROM posting WHERE f=?",(f,)).fetchone()
                data=row[0] if row else b""
                ids=unpack(data);stats["posting_bytes"]+=len(data);stats["posting_calls"]+=1
            if audit_ids is not None:assert tuple(ids)==tuple(audit_ids)
            if not ids or ids[0]>=self.fence:self.known.add(f)
            missing=[]
            for j in ids:
                if j in hot:continue
                b=self.cache.get((EVENT,j))
                if b is None:missing.append(j)
                else:counts.update(unpack(b))
            for start in range(0,len(missing),400):
                batch=missing[start:start+400]
                ph=",".join("?" for _ in batch)
                rows=self.store.db.execute("SELECT members FROM event WHERE j IN ("+ph+") ORDER BY j",batch).fetchall()
                assert len(rows)==len(batch)
                stats["body_calls"]+=1
                for j,(b,) in zip(batch,rows):
                    counts.update(unpack(b));stats["body_bytes"]+=len(b)
                    self.cache.put((EVENT,j),b,admission=f)
                    self.drain()
            # Sufficient to check IDs for membership here: the full incidence sequence is now known.
            cold=[j for j in ids if j not in hot and (EVENT,j) not in self.cache.items]
            alternative=pack_exceptions(len(ids),cold)
            exact=full(ids)
            payload=alternative if len(alternative)<len(exact) else exact
            if payload[0]==EXCEPTION:
                stats["stored_exception_records"]+=1
                stats["stored_exception_ids"]+=len(cold)
            self.cache.put((POST,f),payload)
            self.drain()
        elif audit_ids is not None:
            assert set(hot)==set(audit_ids)
        counts.pop(f,None)
        return best(counts,f,tie,prior),stats
