"""Replay exact bounded directional counts against a persistent pair relation."""
from collections import Counter, deque
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parents[1]/'graph_memory_round44/sql_flow/normalized.json.gz'
CAPS = (1,3,7)
def encode(value, cap):
    if value<0:
        raise ValueError('negative witness count')
    return value if value<=cap else -cap

def update(old, delta, cap, deferred, exact_after):
    """Positive or zero encodes exact, negative encodes a positive lower bound."""
    if old>=0:
        return encode(old+delta,cap)
    bound = -old+delta
    if bound<=0 or (delta<0 and not deferred):
        return encode(exact_after(),cap)
    return -min(cap,bound)

def model_check():
    output={}
    for cap in CAPS:
        for deferred in (False,True):
            seen={(0,0)}
            queue=deque(seen)
            edges=0
            while queue:
                actual,old=queue.popleft()
                for change in range(-4,5):
                    new=actual+change
                    if not 0<=new<=12:
                        continue
                    state=update(old,change,cap,deferred,lambda: new)
                    assert state==new if state>=0 else 1<=-state<=min(cap,new)
                    assert bool(state)==bool(new)
                    vertex=(new,state)
                    if vertex not in seen:
                        seen.add(vertex)
                        queue.append(vertex)
                    edges+=1
            output[f'{cap}-{int(deferred)}']={'states':len(seen),'transitions':edges}
    return output

def replay(traces):
    db=sqlite3.connect(':memory:')
    db.execute('create table pairs (src integer, dst integer, n integer, primary key(src,dst)) without rowid')
    db.execute('create index pair_rev on pairs(dst,src)')
    select=('select coalesce(sum(n),0) from pairs where src=?','select coalesce(sum(n),0) from pairs where dst=?')
    arms=[(k,d) for k in CAPS for d in (False,True)]
    records=[]
    maximum=0
    for trace in traces:
        db.execute('delete from pairs')
        states={arm:{} for arm in arms}
        reads=Counter()
        read_groups=Counter()
        touched=0
        ref=Counter()
        for batch,wanted_rows in trace:
            pair_delta=Counter()
            changes=Counter()
            for src,dst,w in batch:
                pair_delta[src,dst]+=w
                changes[src,0]+=w
                changes[dst,1]+=w
            with db:
                for (src,dst),change in pair_delta.items():
                    if change:
                        db.execute('insert into pairs values (?,?,?) on conflict(src,dst) do update set n=n+excluded.n',(src,dst,change))
                        db.execute('delete from pairs where src=? and dst=? and n=0',(src,dst))
            expected={(i,d) for i,bits in wanted_rows for d in (0,1) if bits & (1<<d)}
            for key,change in changes.items():
                ref[key]+=change
                assert ref[key]>=0
                maximum=max(maximum,ref[key])
                if ref[key]==0:
                    del ref[key]
            assert expected==set(ref)
            touched+=sum(bool(n) for n in changes.values())
            for arm in arms:
                counts=states[arm]
                calls=0
                for key,change in changes.items():
                    if not change:
                        continue
                    def lookup():
                        nonlocal calls
                        calls+=1
                        value=db.execute(select[key[1]],(key[0],)).fetchone()[0]
                        assert value==ref[key]
                        return value
                    state=update(counts.get(key,0),change,*arm,lookup)
                    if state:
                        counts[key]=state
                    else:
                        counts.pop(key,None)
                reads[arm]+=calls
                read_groups[arm]+=int(calls>0)
                assert counts.keys()==expected
            # Both directional outputs above were compared with the independently built fixture.
        records.append({'groups':len(trace),'changes':touched,'arms':{f'{k}-{int(d)}':[reads[k,d],read_groups[k,d]] for k,d in arms}})
    return records,maximum

def main():
    traces=json.loads(gzip.decompress(SOURCE.read_bytes()))
    assert len(traces)==1207 and sum(map(len,traces))==31279
    records,maximum=replay(traces)
    data=(json.dumps(records,separators=(',',':'))+'\n').encode()
    (ROOT/'trace-results.json.gz').write_bytes(gzip.compress(data,mtime=0))
    result={'input_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'protocol_sha256':hashlib.sha256((ROOT/'PROTOCOL_RU.md').read_bytes()).hexdigest(),'records_sha256':hashlib.sha256((ROOT/'trace-results.json.gz').read_bytes()).hexdigest(),'bounded_checks':model_check(),'max_witnesses':maximum,'sqlite':sqlite3.sqlite_version}
    (ROOT/'checks.json').write_text(json.dumps(result,indent=2)+'\n','utf8')
    print('Checked',len(records),'trajectories at six configurations; maximum count',maximum)
if __name__=='__main__':main()
