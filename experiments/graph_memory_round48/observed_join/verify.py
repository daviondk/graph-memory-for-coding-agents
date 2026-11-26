"""Independent archive-free audit against the signed R39/R44 data and native Q32 DP."""
import argparse
import bisect
from collections import Counter,defaultdict
import ctypes as ct
import gzip
import hashlib
import itertools
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

root=Path(__file__).resolve().parent
work=root.parents[1]
def h(b):return hashlib.sha256(b).hexdigest()
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)

def verify():
    if (root/"manifest.json").exists():
        for name,want in read(root/"manifest.json")["files"].items():assert h((root/name).read_bytes())==want,name
    sys.path.insert(0,str(work/"graph_memory_round46/source_sensitivity"))
    import experiment as oracle
    lib,compiler=oracle.compile_kernel()
    def packet(pool):
        prefix=[];left=2048
        for i,c,u in pool:
            if left-c<1024:break
            prefix.append(i);left-=c
        tail=pool[len(prefix):]
        args=(len(tail),left,oracle.arr(ct.c_int,[t[1] for t in tail]),
              oracle.arr(oracle.I,[t[2] for t in tail]),oracle.arr(oracle.BYTE,[0]*len(tail)))
        bits=oracle.pick(lib,args,0)
        return prefix+[t[0] for t,b in zip(tail,bits) if b]
    r39=work/"graph_memory_round39/provenance_packet_demo"
    fixture=work/"graph_memory_round44/sql_flow/normalized.json.gz"
    proof=read(root/"links.json");data=read(root/"projection.json.gz")["queries"]
    result=read(root/"results.json")
    assert h(fixture.read_bytes())==proof["fixture"]
    blob=gzip.decompress(fixture.read_bytes());assert h(blob)==proof["fixture_uncompressed"]
    frame_list=json.loads(blob)
    checked=Counter()
    db=sqlite3.connect((r39/"reader.sqlite").as_uri()+"?mode=ro&immutable=1",uri=True)
    assert h((r39/"reader.sqlite").read_bytes())==proof["reader"]
    by_raw={v["query"]:v["raw_record_sha"] for v in read(r39/"provenance.json")["trajectory_checks"]}
    published={v["trajectory"]:v["number"] for v in read(r39/"panel.json")["queries"]}
    names=[]
    for p in sorted((work/"graph_memory_round44/flow_view").glob("trace-*.json.gz")):
        names.extend(read(p))
    order=sorted(names,key=lambda s:h(("sql-flow-v1/"+s).encode()))
    for q,t in data.items():
        meta=proof["queries"][q]
        lo,hi,d=meta["fixture_span"]
        assert h(blob[lo:hi])==d and meta["raw_record"]==by_raw[q]
        sub=json.loads(blob[lo:hi]);assert sub==frame_list[meta["slot"]]
        assert published[h(order[meta["slot"]].encode())]==q
        assert len(sub)==len(t["steps"])
        end_positions=[r[1] for r in t["steps"]]
        end_events=[r[0] for r in t["steps"]]
        assert sorted(set(end_events))==end_events and sorted(end_positions)==end_positions
        origins={src:(role,pos) for src,role,pos in db.execute("select source,role,position from origin where q=?",(q,))}
        visible={s:bisect.bisect_left(end_positions,pos)+1 for s,(_,pos) in origins.items()}
        assert visible==dict(t["sources"])
        for output,out_step,args,call_step in t["producers"]:
            if output in origins:assert origins[output][0]=="tool_output" and visible[output]==out_step
            if args in origins:assert origins[args][0]=="tool_call" and visible[args]==call_step
            assert output!=args and call_step<=out_step
        span=defaultdict(set)
        for i,s in db.execute("select id,source from span where q=?",(q,)):span[i].add(s)
        rows=[(i,c,round((1<<32)*u)) for i,c,u in db.execute("select id,tokens,utility from node where q=? order by rank",(q,))]
        prev_selected=set();prev_available=set();pairs=Counter();local=Counter();unique=set()
        for step,((group,flags),(event,mark,writes,ids)) in enumerate(zip(sub,t["steps"]),1):
            olds=Counter()
            for (a,b),v in pairs.items():olds[a]+=v
            for a,b,w in group:pairs[a,b]+=w
            assert min(pairs.values(),default=0)>=0
            totals=Counter();bits=defaultdict(int)
            for (a,b),v in pairs.items():
                if v:
                    totals[a]+=v;bits[a]|=1;bits[b]|=2
            assert dict(flags)==dict(bits)
            change={k:(olds[k],totals[k]) for k in set(olds)|set(totals) if olds[k]!=totals[k]}
            assert {a:(old,new) for a,old,new in writes}==change and len(change)==len(writes)
            active=[row for row in rows if span[row[0]] and max(visible[s] for s in span[row[0]])<=step]
            assert packet(active)==ids
            available={s for i,_,_ in active for s in span[i]};selected={s for i in ids for s in span[i]}
            outputs={t["producers"][a][0] for a in change}
            local["joint"]+=len(change)>=2
            local["exact_before"]+=len(outputs&prev_available)>=2
            local["exact_after"]+=len(outputs&available)>=2
            local["selected_before"]+=len(outputs&prev_selected)>=2
            local["selected_after"]+=len(outputs&selected)>=2
            local["same_two_in_both"]+=len(outputs&prev_selected&selected)>=2
            for pair in itertools.combinations(sorted(change),2):
                local["pair_visits"]+=1;local["repeat_pair_visits"]+=pair in unique;unique.add(pair)
            checked["native_packet_comparisons"]+=1
            prev_selected=selected;prev_available=available
        for key,value in local.items():assert result["trajectories"][q].get(key,0)==value
        checked["matched_trajectories"]+=1
    print("PASS:",dict(checked),compiler)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--worker",action="store_true");args=p.parse_args()
    if args.worker:verify()
    else:
        with tempfile.TemporaryDirectory(prefix="observed-join-audit-") as build:
            subprocess.run([sys.executable,"-B",__file__,"--worker"],env=dict(os.environ,SENS_BUILD_DIR=build),check=True)
