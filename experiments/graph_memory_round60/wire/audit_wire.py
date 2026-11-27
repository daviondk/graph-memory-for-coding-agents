"""Derive expected transcripts from source events without sockets, SQLite, or the live serializer."""
from argparse import ArgumentParser
from collections import Counter,defaultdict
from hashlib import sha256
from importlib.util import spec_from_file_location,module_from_spec
from types import SimpleNamespace

from run_wire import HERE,MODES,Coverage,prepare,Hot,SketchPolicy,XOR,possible_losses,load,save
old_path=HERE.parents[1]/"graph_memory_round59"/"transport"/"audit.py"
spec=spec_from_file_location("independent_r59_stream_model",old_path)
old=module_from_spec(spec);spec.loader.exec_module(old)
num=old.var


def framed(content):
    return len(content).to_bytes(4,"big")+content


def graph_trace(ops,cap,mode):
    n=sum(o[0]=="w" for o in ops)//2
    body=SimpleNamespace(events={},postings=defaultdict(list))
    ledger=old.Model(body)
    service=SimpleNamespace(db=ledger,next_id=0)
    hot=Hot();reader=None
    trace=[]
    for o in ops:
        if reader is None and len(body.events)==n:
            reader=Coverage(service,hot,cap,True) if mode=="notify" else SketchPolicy(service,hot,XOR if mode=="xor" else None,cap)
        if o[0]=="w":
            _,j,sha,files=o
            body.events[j]=b"".join(num(i) for i in files)
            for f in files:body.postings[f].append(j)
            service.next_id=j+1
            if reader is not None:
                old_state=dict(hot.live) if mode=="notify" else {}
                hot.append(j,files)
                if mode=="notify":
                    losses=[(i,old_state[i]) for i in sorted(old_state.keys()-hot.live.keys())]
                    reader.after_committed(j,files,losses)
                else:reader.after_write(j,files)
        elif reader is not None:
            _,f,tie,prior,expected=o
            prev=ledger.stats.copy()
            rank,stats=reader.read(f,tie,prior)
            assert rank==expected
            a=ledger.stats-prev
            trace.append([service.next_id,f,a["posting_req_bytes"]+a["bodies_req_bytes"],
                          a["posting_resp_bytes"]+a["bodies_resp_bytes"],a["posting_calls"]+a["bodies_calls"],0,
                          stats["posting_bytes"],stats["body_bytes"],a["posting_req_bytes"],a["posting_resp_bytes"],
                          a["bodies_req_bytes"],a["bodies_resp_bytes"]])
    return trace,ledger.tx.hexdigest(),ledger.rx.hexdigest()


def encode_pairs(items):
    keys=sorted(items)
    out=[num(len(keys))]
    for i,p in enumerate(keys):
        prior=keys[i-1] if i else -1
        out.extend((num(p-prior-1),num(items[p])))
    return b"".join(out)


def server_trace(ops):
    n=sum(o[0]=="w" for o in ops)//2
    events=[];by_file=defaultdict(list)
    prev={}
    wanted=sha256();returned=sha256();trace=[];encoders=Counter()
    for o in ops:
        if o[0]=="w":
            _,j,sha,g=o
            assert j==len(events);events.append(g)
            for i in g:by_file[i].append(j)
        elif len(events)>=n:
            _,f,tie,prior,expected=o
            entire={k:v for k,v in tie.items() if v!=0}
            delta={k:entire.get(k,0) for k in (entire.keys()|prev.keys()) if prev.get(k,0)!=entire.get(k,0)}
            ab=encode_pairs(entire);db=encode_pairs(delta)
            packet=bytes([0])+ab if len(ab)<=len(db) else bytes([1])+db
            encoders["full" if packet[0]==0 else "delta"]+=1
            req=framed(bytes([3])+num(f+1)+num(len(tie))+packet)
            prev=entire
            score=Counter(g for j in by_file.get(f,()) for g in events[j])
            ordered=sorted((k for k in range(len(tie)) if k!=f),key=lambda k:(-score[k],-tie[k],k))[:8]
            assert expected==[(k,score[k]) for k in ordered]
            res=framed(bytes([0])+num(len(ordered))+b"".join(num(k)+num(score[k]) for k in ordered))
            wanted.update(req);returned.update(res)
            trace.append([len(events),f,len(req),len(res),1,len(framed(bytes([3])+num(f+1)))])
    return (trace,wanted.hexdigest(),returned.hexdigest()),encoders


def audit():
    archives=load(HERE.parent/"panel"/"events.json.gz")
    runs=load(HERE/"runs.json.gz")["runs"]
    counts=Counter();results={}
    for repo,stream in archives.items():
        ops,_=prepare(stream,"B")
        hdr,enc=server_trace(ops)
        results[repo]=dict(top8_prior=enc)
        arms={(0,"server"):hdr}
        for cap in (1024,4096):
            for m in ("notify","xor","exact"):arms[cap,m]=graph_trace(ops,cap,m)
        for (cap,m),(trace,tx,rx) in arms.items():
            for b in range(3):
                for lag in (0,2):
                    r=runs[f"{b}/{repo}/{cap}/{m}/{lag}"]
                    assert tx==r["req_sha"] and rx==r["res_sha"]
                    assert trace==[line[:2]+line[3:] for line in r["reads"]]
                    counts.update(stream_hashes=2,per_query_transcripts=len(trace),runs=1)
    return dict(checked=counts,projects=results)


if __name__=="__main__":
    parser=ArgumentParser();parser.add_argument("--verify",action="store_true")
    verify=parser.parse_args().verify;result=audit()
    if verify:assert result==load(HERE/"audit.json")
    else:save(HERE/"audit.json",result)
    print(result["checked"])
