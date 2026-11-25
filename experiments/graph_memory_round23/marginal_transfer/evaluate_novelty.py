"""Measure the marginal evidence contributed by the predicted one-read action."""
from collections import Counter
from pathlib import Path
import runpy
import sys
from select_read import D,c,M
# Reuse only labelled scoring helpers here, after the predictions are sealed.
R=D.parent/"read_causes"
import importlib.util
def loadmodule(name,p):
    spec=importlib.util.spec_from_file_location(name,p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def main():
    lock=c.read(D/"forecast-seal.json")
    for k,n in (("predictions","actions.json.gz"),("plan","PROTOCOL_RU.md"),("clarification","OPERATOR_RU.md"),("script","select_read.py")):
        assert c.checksum(D/n)==lock[k]
    assert c.checksum(M/"novelty.py")==lock["shared"]
    v=c.get_views();sc=runpy.run_path(str(D.parent/"transfer/score.py"),run_name="md2d_scoring")
    gold,issues=sc["labels"](v);assert not issues
    union=sc["union"];overlap=sc["overlap"]
    local=loadmodule("span_inference",R/"score.py")
    old=c.read(D.parent/"transfer/per-query-scores.json.gz")["rows"]
    ref={r["q"]:r for r in old}
    totals={};rows={}
    for q,record in c.read(D/"actions.json.gz").items():
        gt=union(gold[q][0]); doc=gt[0][0];assert all(e==doc for e,l,h in gt)
        required=sum(h-l for e,l,h in gt);base=union(record["base"])
        count=sum(h-l for e,l,h in base);done=overlap(gt,base)
        prev=ref[q]["arms"]["two_ratio"]
        assert prev["full_support"]==int(done==required) and abs(prev["coverage"]-done/required)<1e-12
        values={}
        for k,action in record["actions"].items():
            if action:
                j,(e,l,h,tok),_geom=action
                spans=union(base+[(e,l,h)]) if h>l else base
            else:
                spans=base;tok=0
            credit=overlap(gt,spans); extra=sum(h-l for e,l,h in spans)-count
            assert credit>=done and extra>=0
            values[k]=[int(credit==required),credit/required,credit-done,extra,tok,int(action is None)]
            if k not in totals:totals[k]=[0]*6
            for i,x in enumerate(values[k]):totals[k][i]+=x
        rows[q]={"t":doc,"values":values,"base":[int(done==required),done/required]}
    assert set(rows)==set(ref)
    ordered=[rows[q] for q in sorted(rows)];N=len(ordered)
    pairs=[("rank_novelty","bm25",0),("rank_novelty","first_positive",0)]
    cluster=local.contrasts([r["values"] for r in ordered],[r["t"] for r in ordered],pairs)
    basehits=sum(r["base"][0] for r in ordered)
    summary={k:dict(hits=v[0],additional_hits=v[0]-basehits,coverage=v[1]/N,new_gold_chars=v[2],mean_new_chars=v[3]/N,
       mean_tokens=v[4]/N,no_opens=v[5],new_gold_chars_per_return_token=(v[2]/v[4] if v[4] else None)) for k,v in totals.items()}
    flags=c.save(D/"per-query.json.gz",{"columns":["union_fs","union_coverage","new_gold_chars","new_chars","return_tokens","abstain"],"rows":rows})
    c.save(D/"results.json",{"forecasts":c.checksum(D/"forecast-seal.json"),"primary":cluster,"summaries":summary,"basehits":basehits,
      "q":N,"doc_clusters":len(set(r["t"] for r in ordered)),"values_sha":flags})
    print(basehits,summary,cluster)
if __name__=="__main__":main()
