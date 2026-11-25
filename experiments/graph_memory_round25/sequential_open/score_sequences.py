"""Evaluate only the sealed sequences in original character coordinates."""
from collections import Counter, defaultdict
from pathlib import Path
import runpy
import sqlite3
import numpy as np
from collect import D,R24,S,METHODS,c,read,write,sha
from evaluate_frontier import test

def main():
    lock=read(D/"sequence-lock.json")
    assert lock["protocol"]==sha(D/"PROTOCOL_RU.md") and lock["collector"]==sha(D/"collect.py") and lock["policy"]==sha(D/"policy.py")
    sc=runpy.run_path(str(S/"transfer/score.py"),run_name="md_grounding")
    targets,_=sc["labels"](c.get_views());merge=sc["union"];overlap=sc["overlap"]
    off=D.parents[1]/"graph_memory_round18/isetrace_official";gold=read(off/"gold-spans.json.gz")
    db=sqlite3.connect((S/"read_causes/registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    ids={(t,eid,ptr):e for t,e,eid,ptr in db.execute("select t,e,eid,ptr from address")};db.close()
    corpora={"isetrace":{},"multidoc":{}}
    for name,digest in sorted(lock["files"].items()):
        assert sha(D/name)==digest
        ise=name.startswith("ise-");corpus=corpora["isetrace" if ise else "multidoc"]
        for q,r in read(D/name).items():
            if ise:
                group=r["trace"];gt=merge([(ids[group,x["event_id"],x["json_pointer"]],x["char_start"],x["char_end"]) for x in gold[q]])
            else:
                gt=merge(targets[q][0]);group=gt[0][0]
            total=sum(h-l for _,l,h in gt);base=merge(r["base"]);initial=overlap(gt,base);start_chars=sum(h-l for _,l,h in base)
            def metrics(actions):
                sel=merge(base+[(e,l,h) for e,l,h,_ in actions if l<h])
                hits=overlap(gt,sel)
                tokens=sum(p[3] for p in actions)
                assert initial<=hits<=total and all(0<=a[3]<=256 for a in actions) and len(actions)<=4
                return [int(hits==total),hits/total,tokens,len(actions),len({e for e,_,_,_ in actions}),sum(h-l for _,l,h in sel)-start_chars]
            row={}
            for method in METHODS:
                path=r["actions"][method]
                for i in range(1,5):
                    row[method+"/"+str(i)]=metrics(path[:i])
                row[method+"/cap"]=metrics(r["cap"][method])
                assert row[method+"/cap"][2]<=768
            for ctrl,pair in r["equal"].items():
                a,b=map(metrics,pair)
                assert a[2]==b[2]<=768
                row["tail_eq/"+ctrl]=a;row["control_eq/"+ctrl]=b
            assert q not in corpus
            corpus[q]={"base":metrics([]),"g":group,"steps":row}
    outcomes={}
    primary=[]
    for tag,rows in corpora.items():
        ordered=[rows[q] for q in sorted(rows)];n=len(rows)
        assert (n,sum(r["base"][0] for r in ordered))==((2000,1671) if tag=="isetrace" else (661,444))
        keys=ordered[0]["steps"].keys()
        totals={}
        for key in keys:
            arr=np.array([r["steps"][key] for r in ordered])
            totals[key]={"hits":int(arr[:,0].sum()),**dict(zip(("coverage","tokens","calls","fields","new_chars"),arr[:,1:].mean(axis=0).tolist()))}
        assert totals["any/1"]["hits"]==(1710 if tag=="isetrace" else 456)
        pairs={}
        for left,right in (("tail/cap","any/cap"),("tail/cap","balanced/cap"),("any/cap","frozen/cap"),("balanced/cap","first/cap"),("tail_eq/any","control_eq/any"),("tail_eq/balanced","control_eq/balanced")):
            diffs=[r["steps"][left][0]-r["steps"][right][0] for r in ordered]
            effect=test(diffs,[r["g"] for r in ordered]);pairs[left+" vs "+right]=effect
            if left=="tail/cap":primary.append(effect)
        outcomes[tag]={"n":n,"starting_hits":sum(r["base"][0] for r in ordered),"clusters":len({r["g"] for r in ordered}),"summary":totals,"paired":pairs}
    highest=0
    for j,p in enumerate(sorted(primary,key=lambda x:x["p_signflip"])):
        highest=max(highest,min(1.0,p["p_signflip"]*(4-j)));p["holm_p"]=highest
    write(D/"per-query.json.gz",{"columns":["full_support","coverage","extra_tokens","calls","unique_fields","extra_source_chars"],"corpora":corpora})
    write(D/"results.json",{"seal":sha(D/"sequence-lock.json"),"outcomes":sha(D/"per-query.json.gz"),"corpora":outcomes})
    for tag,r in outcomes.items():
        print(tag,{m:r["summary"][m+"/cap"] for m in METHODS})
if __name__=="__main__": main()
