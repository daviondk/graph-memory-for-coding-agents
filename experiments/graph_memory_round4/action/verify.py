"""Independently reparse the packed wire logs, reconstruct every response, and reconcile every byte."""
from concurrent.futures import ProcessPoolExecutor
from collections import Counter
import hashlib,json
from codec import receive,whole_frame
from delta import canonical,input_wire,receive as rdelta
from optimistic import reconstruct
from experiment import D,dec,digest,locations,mem,read,rows,write

def one(job):
    panel,j=job
    n=0;counts=Counter();sumbytes=Counter();rounds=Counter()
    i,g,_,_,_=locations(panel,j)
    traces=rows(D/f"opt_raw_{panel}_{j}.jsonl.gz")
    costs=rows(D/f"opt_cost_{panel}_{j}.jsonl.gz")
    for inp,truth,trace,score in zip(rows(i),rows(g),traces,costs,strict=True):
        issue,repo,t,path,vr,blobs=inp
        assert (issue,t)==(truth[0],truth[1])==(trace[0],trace[1])==(score[0],score[2])
        current={n:s.encode() for n,s in truth[2]}
        wanted=canonical(current);n+=1
        assert trace[4]==hashlib.sha256(wanted).hexdigest()
        known=mem(blobs['lru'],path,vr)
        authoritative=whole_frame(current);rawbytes=[dec(z) for z in trace[2]]
        for k,indices in trace[3].items():
            wire=[rawbytes[r] for r in indices];req=wire[::2];res=wire[1::2]
            sq=sum(map(len,req));sr=sum(map(len,res))
            assert [sq+sr,sq,sr,len(req)]==score[3][k]
            if k=="rolling256":
                original=canonical({n:v[0] for n,v in known.items()});formatted,blocks=input_wire(path,vr,original,256)
                assert formatted==req[0] and rdelta(res[0],blocks)==wanted and len(req)==1
            elif k=="optim":
                recovered=reconstruct(req[0],res[0],known)
                if recovered is None:
                    assert len(req)==2 and res[1]==authoritative
                    recovered=reconstruct(req[1],res[1],{})
                else:assert len(req)==1
                assert recovered==current
            else:assert len(req)==1 and receive(req[0],res[0],known)==current
            counts[k]+=1;sumbytes[k]+=sq+sr;rounds[k]+=len(req)
    return (panel,n,counts,sumbytes,rounds)
def main():
    expected=read(D/"opt_results.json")
    record={k:dict(actions=0,exact=Counter(),bytes=Counter(),rounds=Counter()) for k in "ABC"}
    with ProcessPoolExecutor(4) as pool:
        for panel,n,c,b,r in pool.map(one,[(p,j) for p in "ABC" for j in range(8)]):
            s=record[panel];s["actions"]+=n;s["exact"].update(c);s["bytes"].update(b);s["rounds"].update(r)
    for panel,s in record.items():
        assert s["actions"]==expected[panel]["views"]
        for m,n in s["exact"].items():
            assert n==s["actions"] and s["bytes"][m]==expected[panel]["methods"][m]["bytes"] and s["rounds"][m]==expected[panel]["methods"][m]["round_trips"]
    for name in ("decision_lock.json","opt_lock.json","input_lock.json","request_lock.json"):
        assert all(digest(D/n)==v for n,v in read(D/name).items())
    assert all(digest(D/n)==v for n,v in read(D/"delta_lock.json")["hashes"].items())
    write(D/"wire_audit.json",record)
    print({p:s['actions'] for p,s in record.items()},"frames decoded",sum(sum(s['exact'].values()) for s in record.values()),flush=True)
if __name__=="__main__":main()
