"""Grade all equal-budget policies, on the two retrospective panels and the sealed transfer."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import math

import numpy as np
from scipy.stats import binomtest
from study import HERE, SOURCE, raw, save, digest, ci_records
from verify import score

PATHS={"adaptive_address":SOURCE/"adaptive_address", "gate_confirmation":SOURCE/"gate_confirmation",
       "hotpot":HERE.parent/"transfer"}
METRICS=["full","recall","f1","em"]
PAIRS=[("graph","hybrid"),("graph","dense"),("graph","linked"),("graph","gate"),
       ("hybrid","dense"),("gate","dense"),("graph_pair","gate"),("answer_pair","gate")]


def module(path,expected):
    assert digest(path)==expected
    sys.modules.setdefault("ujson",json)
    spec=importlib.util.spec_from_file_location("author_"+expected[:5],path)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def main(official):
    ctx=raw(HERE/"matched-contexts.json.gz")
    inputs=raw(HERE/"completion-input-seal.json")
    receipt=raw(HERE/"completion-answer-seal.json")
    assert inputs["contexts"]==digest(HERE/"matched-contexts.json.gz")
    assert receipt["inputs"]==digest(HERE/"completion-input-seal.json")
    assert receipt["outputs"]==digest(HERE/"new-answers.json.gz")
    assert all(z["expected"]==z["observed"] for g in raw(HERE/"reader-replay.json").values() for z in g.values())
    hot_seal=raw(HERE/"hotpot-decision-seal.json")
    assert hot_seal["choices"]==digest(HERE/"hotpot-decisions.json.gz")
    outputs=raw(HERE/"new-answers.json.gz")
    extra=set(outputs)
    if official:
        two=module(Path("D:/CodexResearch/x20-r50-qa-external/author_evaluate.py"),
                   "7c09ee2ec98c7ecb57df79eb68dba22eb381ab58d50e730dfcefafb4dda31458")
        hot=module(Path("D:/CodexResearch/x20-r51-hotpot-gate/official.py"),
                   "d35fc91a6db21d791dbdda11daf3856e9359f5701d54e3eefba20d88fecc02c0")
    results,records={},{}
    for p,path in PATHS.items():
        for k,answer in raw(path/"answers.json.gz").items():
            assert outputs.setdefault(k,answer)==answer
        gold=raw(path/"gold.json.gz")
        sample=ctx[p]
        n=len(sample)
        assert set(sample)==set(gold) and len({z["cluster"] for z in sample.values()})==n
        records[p]={}
        for q,case in sample.items():
            if p=="hotpot":
                labels=gold[q]; refs=[labels["answer"]];titles=labels["titles"];support=labels["support_titles"]
            else: refs,titles,support=gold[q]
            support=set(support)
            row={}
            for a,(i,k,L) in case["refs"].items():
                s=outputs[k]["answer"]; em,f1=score(s,refs)
                if official:
                    if p=="hotpot":
                        assert em==hot.exact_match_score(s,refs[0])
                        assert abs(f1-hot.f1_score(s,refs[0])[0])<1e-12
                    else:
                        stats=dict(em=0.,f1=0.,prec=0.,recall=0.)
                        two.update_answer(stats,s,refs)
                        assert em==stats["em"] and abs(f1-stats["f1"])<1e-12
                hits={titles[case["first"]],titles[i]}&support
                row[a]=dict(full=int(len(hits)==len(support)),recall=len(hits)/len(support),
                            f1=f1,em=em,new=k in extra)
            records[p][q]=row
        vals=records[p]; qs=sorted(vals)
        policies={a:{**{m:math.fsum(vals[q][a][m] for q in qs)/n for m in METRICS},
                     "new_answer_questions":sum(vals[q][a]["new"] for q in qs),
                     "changed_address":sum(sample[q]["refs"][a][0]!=sample[q]["refs"]["dense"][0] for q in qs)}
                  for a in vals[qs[0]]}
        diffs=[];keys=[]
        for a,b in PAIRS:
            for m in METRICS:
                keys.append((a,b,m))
                diffs.append([vals[q][a][m]-vals[q][b][m] for q in qs])
        arr=np.array(diffs).T
        estimates=ci_records(arr,np.random.default_rng(510271))
        contrasts={}
        for (a,b,m),ds,(d,lo,hi) in zip(keys,diffs,estimates):
            pos,neg=sum(x>1e-12 for x in ds),sum(x< -1e-12 for x in ds)
            o=dict(delta_pp=d,ci95_pp=[lo,hi],gains=pos,losses=neg)
            if m=="full":o["exact_mcnemar"]=float(binomtest(pos,pos+neg,.5).pvalue) if pos+neg else 1.
            contrasts.setdefault(a+"-"+b,{})[m]=o
        changed={q:[sample[q]["original_n"],sample[q]["n"]] for q in qs if sample[q]["original_n"]!=sample[q]["n"]}
        results[p]={"n":n,"unique_clusters":n,"new_unique":len({
            k for q in qs for i,k,L in sample[q]["refs"].values() if k in extra}),
            "shortened":changed,"policies":policies,"contrasts":contrasts}
    save("complete-records.json.gz",records)
    save("complete-results.json",results)
    if official:
        save("scoring-receipt.json",{"results":digest(HERE/"complete-results.json"),
             "records":digest(HERE/"complete-records.json.gz"),"n_scored":sum(z["n"]*len(z["policies"]) for z in results.values()),
             "2wiki":"7c09ee2ec98c7ecb57df79eb68dba22eb381ab58d50e730dfcefafb4dda31458",
             "hotpot":"d35fc91a6db21d791dbdda11daf3856e9359f5701d54e3eefba20d88fecc02c0"})
    print("Scored",sum(x["n"] for x in results.values()),"queries and verified official graders:",official)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official",action="store_true")
    main(parser.parse_args().official)
