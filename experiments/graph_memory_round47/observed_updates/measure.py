"""Count transactions in normalized positive/negative tool-value provenance ledgers."""
from collections import Counter
import gzip
import hashlib
import itertools
import json
from pathlib import Path
D=Path(__file__).resolve().parent
INPUT=D.parents[1]/'graph_memory_round44/sql_flow/normalized.json.gz'
def measure(trace):
    pool=Counter();source_total=Counter()
    rows={k:Counter() for k in ('net_count','edge_changed','flag_changed')}
    frequency={k:Counter() for k in rows}
    signs=Counter()
    for batch,ref in trace:
        before={s for s,n in source_total.items() if n>0}
        edge_delta=Counter()
        for a,b,d in batch:
            edge_delta[a,b]+=d
        changed=Counter()
        for key,d in edge_delta.items():
            if not d:continue
            a,b=key
            pool[key]+=d;changed[a]+=d;source_total[a]+=d
            assert pool[key]>=0
        after={s for s,n in source_total.items() if n>0}
        assert after=={i for i,mask in ref if mask&1}
        keys={'net_count':{a for a,d in changed.items() if d},'edge_changed':{a for (a,b),d in edge_delta.items() if d},'flag_changed':before^after}
        for k,group in keys.items():
            s=rows[k];s['groups']+=1;s['any']+=int(bool(group));s['joint']+=int(len(group)>=2)
            s['endpoints']+=len(group)
            for a,b in itertools.combinations(sorted(group),2):
                s['visits']+=1
                s['hits']+=int(frequency[k][a,b]>0)
                frequency[k][a,b]+=1
                if k=='net_count':
                    signs['two_gains' if changed[a]>0 and changed[b]>0 else 'two_losses' if changed[a]<0 and changed[b]<0 else 'mixed']+=1
    for k,c in frequency.items():
        rows[k].update({'unique':len(c),'singletons':sum(v==1 for v in c.values()),'repeat_keys':sum(v>=2 for v in c.values()),'max_visits':max(c.values(),default=0)})
    return {'metrics':rows,'signs':signs}
def main():
    allrows=json.loads(gzip.decompress(INPUT.read_bytes()))
    outcome=[measure(t) for t in allrows]
    data=(json.dumps(outcome,separators=(',',':'),sort_keys=True)+'\n').encode()
    (D/'traces.json.gz').write_bytes(gzip.compress(data,mtime=0))
    seal={'n':len(outcome),'sha_input':hashlib.sha256(INPUT.read_bytes()).hexdigest(),'sha_rows':hashlib.sha256((D/'traces.json.gz').read_bytes()).hexdigest(),'sha_protocol':hashlib.sha256((D/'PROTOCOL_RU.md').read_bytes()).hexdigest()}
    (D/'seal.json').write_text(json.dumps(seal,indent=2)+'\n','utf8')
    print(len(outcome))
if __name__=='__main__':main()
