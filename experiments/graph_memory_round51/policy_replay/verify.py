"""Recompute switches, costs, equivalence classes, subgroup-free metrics and the cache-key control."""
import argparse
from fractions import Fraction
from itertools import chain
import math
from pathlib import Path
import sqlite3

import replay


def frozen_data(panel):
    names=("contexts.json.gz","orders.json.gz","outcomes.json.gz","answers.json.gz","threshold-seal.json")
    return replay.source(panel,names)

def check_panel(db,panel,results,witness):
    data=frozen_data(panel)
    threshold=data["threshold-seal"]["primary"]
    outcomes=data["outcomes"]
    n=len(outcomes)
    assert n==len({r["cluster"] for r in outcomes.values()})
    ids=sorted(outcomes)
    measurements={}
    # Reconstruct partitions from ALL candidates, independent of the SQLite construction.
    for q in ids:
        r=data["orders"][q]
        group=set(r["edges"])
        scores={int(k):Fraction.from_float(v) for k,v in r["scores"].items()}
        rank=r["order"]
        plain=max(rank,key=lambda i:scores[i])
        inc=max((i for i in rank if i in group),key=lambda i:scores[i],default=plain)
        gap=scores[plain]-scores[inc]
        if plain!=inc:
            assert float(gap)==gap
        refs=data["contexts"][q]["refs"]
        assert (refs["dense"][0],refs["linked_dense"][0])==(plain,inc)
        measurements[q]=(None if inc==plain else float(gap),refs["dense"][1],refs["linked_dense"][1])
        if plain!=inc:
            # A rounded floating-point addition could mask a one-ULP offset.
            for t in (math.nextafter(float(gap),-math.inf),float(gap),math.nextafter(float(gap),math.inf)):
                val=Fraction.from_float(t)
                exact=max(rank,key=lambda i:(scores[i]+(val if i in group else 0),i in group))
                assert exact==(inc if val>=gap else plain)
    for arm1,arm2,name in (("dense","adaptive","dense-to-registered"),
                            ("dense","linked_dense","dense-to-always"),
                            ("linked_dense","adaptive","always-to-registered")):
        report=results[name]
        cache=set()
        full=set()
        leftkeys=set()
        rightkeys=set()
        dense_diffs={}
        for q in ids:
            c=data["contexts"][q]["refs"]
            left,right=c[arm1],c[arm2]
            full.update((left[1],right[1]))
            leftkeys.add(left[1]); rightkeys.add(right[1])
            diffs=[b-a for a,b in zip(outcomes[q]["arms"][arm1][:2],outcomes[q]["arms"][arm2][:2])]
            dense_diffs[q]=diffs
            if left[1]!=right[1]:
                cache.update((left[1],right[1]))
        sparse={row[0]:row[3:5] for row in witness[name]}
        assert len(sparse)==report["changed_input"]
        assert all(dense_diffs[q]==sparse.get(q,[0,0]) for q in ids)
        assert math.isclose(100*math.fsum(dense_diffs[q][1] for q in ids)/n,report["delta_f1_pp"],abs_tol=1e-13)
        tokens={x[1]:x[2] for q in ids for x in data["contexts"][q]["refs"].values()}
        for keys,k in ((full,"cold_memoized"),(cache,"cold_delta"),(leftkeys,"absolute_start"),(rightkeys-leftkeys,"warm_new_calls")):
            assert report[k]==dict(calls=len(keys), input_tokens=sum(tokens[h] for h in keys),
                                   output_tokens=sum(data["answers"][h]["tokens"] for h in keys))
    gaps=sorted({g for g,a,b in measurements.values() if g is not None})
    points=sorted(set(chain([-1.,0.,threshold,2.],(v for g in gaps for v in (math.nextafter(g,-math.inf),g,math.nextafter(g,math.inf))))))
    # Check every threshold equivalence class and boundaries of representable neighbors.
    for t in points:
        expected={q:(a,b) for q,(g,a,b) in measurements.items() if g is not None and g<=t and a!=b}
        assert replay.crossing_plan(db,panel,-1.,t)==expected
        assert replay.crossing_plan(db,panel,t,-1.)=={q:(b,a) for q,(a,b) in expected.items()}
    return {"questions":n,"distinct_gaps":len(gaps),"cutoffs_verified":len(points),"dense_to_cutoff_and_reverse_vectors":2*len(points),
            "question_differences_verified_over_cutoffs":2*n*len(points)}

def control():
    names=("contexts.json.gz","answers.json.gz","outcomes.json.gz","answer-seal.json")
    a,b=[replay.source(x,names) for x in ("qa_replication","semantic_address")]
    assert replay.snapshot(a["answer-seal"])==replay.snapshot(b["answer-seal"])
    assert set(a["contexts"])==set(b["contexts"])
    rows=[]
    for q in sorted(a["contexts"]):
        c,d=a["contexts"][q],b["contexts"][q]
        i,h,k=c["refs"]["lex"]
        j,g,m=d["refs"]["lex"]
        assert (i,c["seed"],c["cluster"])==(j,d["seed"],d["cluster"])
        answers=[s["answers"][key]["answer"] for s,key in ((a,h),(b,g))]
        f1=[s["outcomes"][q]["arms"]["lex"][1] for s in (a,b)]
        rows.append(dict(question=q,second=i,first=c["seed"],old_tokens=k,new_tokens=m,
                         old_prompt=h,new_prompt=g,answer_changed=answers[0]!=answers[1],
                         f1_old=f1[0],f1_new=f1[1]))
        if h==g:
            assert answers[0]==answers[1] and f1[0]==f1[1]
    return rows

def fixtures():
    db=sqlite3.connect(":memory:")
    db.execute("CREATE TABLE routes(panel,question,gap,dense,linked)")
    db.executemany("INSERT INTO routes VALUES('p',?,?,?,?)",[
        ("identical-input",0.2,"token-key-1","token-key-1"),("tie",0,"A","B"),("gap",0.2,"X","Y"),("no-edge",None,"J","J")])
    assert replay.crossing_plan(db,"p",-1,0)=={"tie":("A","B")}
    assert replay.crossing_plan(db,"p",math.nextafter(.2,-math.inf),.2)=={"gap":("X","Y")}
    assert not replay.crossing_plan(db,"p",.2,.2)
    seal={k:"same" for k in ("model","engine","inference","client","props")}
    for k in seal:
        assert replay.snapshot(dict(seal,**{k:"different"}))!=replay.snapshot(seal)
    db.close()

def main(dest,record=False):
    fixtures()
    db=sqlite3.connect(":memory:")
    replay.build(db)
    results=replay.read(dest/"results.json")
    full={p:check_panel(db,p,results["panels"][p],replay.read(dest/(p+"-witnesses.json.gz"))) for p in replay.PANELS}
    limit=control()
    summary=dict(pairs=len(limit),different_prompts=sum(r["old_prompt"]!=r["new_prompt"] for r in limit),
                 different_answers=sum(r["answer_changed"] for r in limit),
                 different_f1=sum(r["f1_old"]!=r["f1_new"] for r in limit))
    full["same_document_control"]=summary
    if record:
        replay.dump(dest/"verification.json",full)
        (dest/"control.json.gz").write_bytes(replay.gzip.compress(replay.json.dumps(limit,separators=(",",":")).encode(),mtime=0))
    else:
        assert replay.read(dest/"verification.json")==full and replay.read(dest/"control.json.gz")==limit
    print(replay.json.dumps(full,indent=2))
    db.close()

if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record",action="store_true")
    ap.add_argument("--output",type=Path,default=replay.ROOT)
    opts=ap.parse_args()
    main(opts.output,opts.record)

