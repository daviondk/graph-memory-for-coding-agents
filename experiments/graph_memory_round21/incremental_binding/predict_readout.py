"""Freeze graph reads before opening evidence labels."""
from collections import defaultdict
import gzip
import hashlib
import json
import math
import random
import sys
from pathlib import Path
from evaluate import D, R20, env, save, FeedIndex, parse_isetrace_record, adapt_isetrace_record
sys.path.insert(0,str(D.parent/"factorized_provenance"))
from study import geometry,ref
from operators import Packed, features_in_rank_order, rank_strength, packed_stats, table
import numpy as np

ARMS=("exact","append","half","shuffled")


def structure(tr,g,ids,geom):
    live=FeedIndex()
    calltime={};outputtime={}
    for event in tr.events:
        live.consume(event)
        pos=(event.position.message_index,event.position.sub_index)
        if event.event_type=="tool_call":calltime[event.call_id]=pos
        elif event.event_type=="tool_output":outputtime[event.call_id]=pos
    groups={}
    for n in g["nodes"]:
        if n["kind"]==ref.OUTPUT_CHUNK_NODE:
            call=n["attributes"]["call_id"]; group=int(geom.membership[ids[n["node_id"]]])
            assert call not in groups or group==groups[call]
            groups[call]=group
    observed={(groups[a],groups[b]) for a,b in live.support if a in groups and b in groups}
    native={(int(a),int(b)) for a,b,k in geom.links if k==2}
    assert observed==native, tr.trajectory_id
    extra={(groups[a],groups[b]) for a,b in live.ever-set(live.support) if a in groups and b in groups}
    rev={v:k for k,v in groups.items()};assert len(rev)==len(groups)
    perm=set(extra);seq=sorted(extra);swaps=0
    if len(seq)>1:
        rng=random.Random("incremental-rewire-v1"+tr.trajectory_id)
        for _ in range(10*len(seq)):
            i,j=rng.sample(range(len(seq)),2);a,b=seq[i];c,d=seq[j]
            if a==c or b==d or a==d or c==b:continue
            if (a,d) in perm or (c,b) in perm or (a,d) in native or (c,b) in native:continue
            if outputtime[rev[a]]>=calltime[rev[d]] or outputtime[rev[c]]>=calltime[rev[b]]:continue
            perm.difference_update(((a,b),(c,d)));perm.update(((a,d),(c,b)));seq[i]=(a,d);seq[j]=(c,b);swaps+=1
    for k in (0,1):
        assert sorted(e[k] for e in extra)==sorted(e[k] for e in perm)
    def extended(xs):
        add=table(((a,b,2) for a,b in sorted(xs)),3)
        return Packed(geom.membership,geom.adjacent,np.vstack((geom.links,add)))
    return extended(extra),extended(perm),dict(extra=len(extra),changed=len(extra-perm),swaps=swaps,exact=len(native))


def run():
    tids={r["t"] for r in env.load(env.TR/"split.json.gz")["test"]}
    pilot=set(json.loads((D/"plan.json").read_bytes())["trajectories"])
    gra=ref.graph_index();weights=ref.read(R20/"typed_reader/weights.json")["typed"];w=np.array(weights["w"])
    locks=ref.read(R20/"typed_reader/prediction-plan.json")
    orig=ref.read(R20/"typed_reader/forecast-seal.json")
    sources={r["path"]:r["sha256"] for r in ref.read(env.R18/"isetrace_official/source-lock.json")}
    outputs={};diags=[];seen=set()
    for i in range(8):
        fn=f"forecasts-main-{i}.json.gz"
        assert ref.sha(ref.TR/fn)==locks["test"][fn]
        forecast=R20/f"typed_reader/forecast-{i}.json.gz"
        assert ref.sha(forecast)==orig["forecasts"][forecast.name]
        previous={r["q"]:r["selection"]["typed"] for r in ref.read(forecast)}
        source=env.RAW/f"trajectories-{i:05d}.jsonl"
        assert ref.sha(source)==sources["trajectories/"+source.name]
        by=defaultdict(list)
        for r in ref.read(ref.TR/fn):by[r["t"]].append(r)
        rows=[]
        for raw,obj in env.pilot.stream(source):
            t=obj["session_id"]
            if t not in by:continue
            seen.add(t);tr=adapt_isetrace_record(parse_isetrace_record(obj),source_revision=env.pilot.RAW[1])
            rp,digest=gra[t];assert ref.sha(rp)==digest
            record=ref.read(rp);assert record["raw_source"]==hashlib.sha256(raw).hexdigest()
            ids,g=geometry(record);ext,shuf,diag=structure(tr,record["g"],ids,g)
            diags.append(dict(t=t,pilot=t in pilot,**diag))
            for r in by[t]:
                rr=r["rr"];cost=[n["token_count"] for n in rr]
                order=np.array([ids[n["node_id"]] for n in rr]);st=rank_strength(order)
                def score(geom):
                    return features_in_rank_order(order,packed_stats(geom,st))@w+weights["bias"]
                first=score(g);second=score(ext)
                scores={"exact":first,"append":second,"half":(first+second)/2,"shuffled":score(shuf)}
                picks={k:ref.pack(np.argsort(-v,kind="stable"),cost,False) for k,v in scores.items()}
                assert picks["exact"]==previous[r["q"]]["prefix"]
                rows.append(dict(t=t,q=r["q"],pilot=t in pilot,picks=picks))
        out=D/f"readout-{i}.json.gz";save(out,rows);outputs[out.name]=ref.sha(out)
        print("sealed shard",i,len(rows),flush=True)
    assert seen==tids and len(diags)==1207
    save(D/"readout-graph-audit.json.gz",diags)
    save(D/"readout-lock.json",{"forecasts":outputs,"graph_audit":ref.sha(D/"readout-graph-audit.json.gz"),
         "code":ref.sha(D/"predict_readout.py"),"protocol":ref.sha(D/"READOUT_PROTOCOL_RU.md"),"stream":ref.sha(D/"stream.py"),
         "operators":ref.sha(D.parent/"factorized_provenance/operators.py"),"reader":ref.sha(R20/"typed_reader/weights.json"),
         "pilot":ref.sha(D/"plan.json")})


if __name__=="__main__":run()
