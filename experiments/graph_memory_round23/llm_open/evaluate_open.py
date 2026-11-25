"""Validate sealed SQL receipts and score source provenance rather than generated claims."""
from collections import defaultdict
import importlib.util
import math
import sqlite3
import statistics
import sys
from prepare import D,SOURCE,AB,read,sha,write
import numpy as np
from scipy.stats import binomtest
module=importlib.util.spec_from_file_location("source_measures",SOURCE/"score.py")
m=importlib.util.module_from_spec(module);module.loader.exec_module(m)
def bounds(k,n):
    if not n:return None
    z=1.95996398454;p=k/n;a=1+z*z/n
    center=(p+z*z/(2*n))/a;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/a
    return [max(0,center-half),min(1,center+half)]
def pair(delta):
    a=np.array(delta);n=len(a);pos=int((a==1).sum());neg=int((a==-1).sum())
    rng=np.random.default_rng(230423)
    boot=a[rng.integers(0,n,size=(20000,n))].mean(axis=1)
    return dict(n=n,wins=pos,losses=neg,delta=float(a.mean()),paired_boot95=np.quantile(boot,[.025,.975]).tolist(),
                exact_p=float(binomtest(pos,pos+neg).pvalue) if pos+neg else 1.0)
def main():
    seal=read(D/"open-seal.json")
    assert sha(D/"sql-reads.json.gz")==seal["reads"] and sha(D/"sql-queries.json.gz")==seal["log"] and sha(D/"reader-lock.json")==seal["reader"]
    gold_path=D.parents[1]/"graph_memory_round18/isetrace_official/gold-spans.json.gz"
    truth=read(gold_path)
    db=sqlite3.connect((SOURCE/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    rows=read(D/"sql-reads.json.gz");menu={r["q"]:r for r in read(D/"menus.json.gz")};records=[]
    for r in rows:
        q,t=r["q"],r["t"];refs=[]
        for s in truth[q]:
            x=db.execute("SELECT e FROM address WHERE t=? AND eid=? AND ptr=?",(t,s["event_id"],s["json_pointer"])).fetchone()
            refs.append([x[0] if x else -1,s["char_start"],s["char_end"]])
        row={"q":q,"t":t,"one_field":len({(s["event_id"],s["json_pointer"]) for s in truth[q]})==1,"fmt":{}}
        for fmt, arm in r["arms"].items():
            mm=menu[q]["arms"][fmt]
            def grade(v):
                e,a,b=v["span"]
                z,_=m.measure(refs,[(e,a,b)] if b>a else [])
                return dict(full=z[0],coverage=z[2],any=int(z[2]>0),field=int(e>=0 and any(d==e for d,l,h in refs)),tokens=v["tokens"])
            options=[grade(x) for x in arm["options"]]
            opened={k:grade(v) for k,v in arm["opened"].items()}
            initial=m.measure(refs,mm["parent_visible"])[0]
            preview=m.measure(refs,mm["displayed"])[0]
            row["fmt"][fmt]={"opened":opened,"original_full":initial[0],"original_coverage":initial[2],"preview_full":preview[0],
                    "preview_coverage":preview[2],"possible":max(z["full"] for z in options),"possible_cov":max(z["coverage"] for z in options),
                    "n_menu":len(options),"wp":mm["wp"],"wp_preview":mm["wp_preview"],"ok":arm["ok"],"qwen_prompt":arm["usage"][0],
                    "qwen_completion":arm["usage"][1],"choices":arm["chosen"]}
        a,b=menu[q]["arms"]["short"],menu[q]["arms"]["merged"]
        row["same_request"]=a["request"]==b["request"]
        row["same_set"]={tuple(x) for x in a["candidates"]}=={tuple(x) for x in b["candidates"]}
        row["same_order"]=a["candidates"]==b["candidates"]
        records.append(row)
    db.close()
    assert len(records)==len({r["t"] for r in records})==32
    summaries={}
    rates=("original_full","preview_full","possible","original_coverage","preview_coverage","possible_cov","n_menu","wp","wp_preview","qwen_prompt","qwen_completion")
    for fmt in ("short","merged"):
        z=[r["fmt"][fmt] for r in records]
        stats={k:statistics.fmean(r[k] for r in z) for k in rates}
        stats["policy"]={}
        for k in z[0]["opened"]:
            rec=[r["opened"][k] for r in z]
            rr={name:statistics.fmean(u[name] for u in rec) for name in rec[0]}
            rr["successes"]=sum(u["full"] for u in rec);rr["wilson95"]=bounds(rr["successes"],len(rec))
            stats["policy"][k]=rr
        stats["reach_count"]=sum(r["possible"] for r in z)
        stats["conditional_qwen_given_reachable"]=stats["policy"]["qwen"]["successes"]/stats["reach_count"] if stats["reach_count"] else None
        stats["qwen_agrees_with"]={k:sum(r["choices"]["qwen"]==r["choices"][k] for r in z) for k in ("first","bm25","bm25_before")}
        stats["successful_open_without_full_preview"]=sum(not r["preview_full"] and r["opened"]["qwen"]["full"] for r in z)
        stats["full_preview_but_open_incomplete"]=sum(r["preview_full"] and not r["opened"]["qwen"]["full"] for r in z)
        summaries[fmt]=stats
    def delta(r,f="full"):
        return r["fmt"]["merged"]["opened"]["qwen"][f]-r["fmt"]["short"]["opened"]["qwen"][f]
    prim=pair([delta(r) for r in records]);succeeded=[r for r in records if all(a["ok"] for a in r["fmt"].values())]
    extras={fmt+"-qwen-vs-"+method:pair([r["fmt"][fmt]["opened"]["qwen"]["full"]-r["fmt"][fmt]["opened"][method]["full"] for r in records]) for fmt in ("short","merged") for method in ("first","bm25","bm25_before")}
    assert all(v["fmt"]["short"]["wp"]==v["fmt"]["merged"]["wp"] for v in records)
    q_diff=[v["fmt"]["merged"]["qwen_prompt"]-v["fmt"]["short"]["qwen_prompt"] for v in succeeded]
    raw=D/"scored.json.gz";write(raw,records)
    write(D/"results.json",dict(n=len(records),one_field_n=sum(x["one_field"] for x in records),complete_pairs=len(succeeded),summary=summaries,
        primary=prim,successful_pairs=pair([delta(r) for r in succeeded]) if succeeded else None,descriptive_qwen_controls=extras,
        prompt_wp_delta_all_zero=True,qwen_prompt_token_delta_merged_minus_short=dict(min=min(q_diff),max=max(q_diff),mean=statistics.fmean(q_diff),
            mean_absolute=statistics.fmean(map(abs,q_diff))) if q_diff else None,
        identical_prompt=sum(r["same_request"] for r in records),identical_order=sum(r["same_order"] for r in records),identical_offered_set=sum(r["same_set"] for r in records),
        raw=sha(raw),seal=sha(D/"open-seal.json"),gold_sha=sha(gold_path),code=sha(__file_as_path())))
    print("result",sha(D/"results.json"),prim)
    for f in summaries:
        print(f,{k:v["successes"] for k,v in summaries[f]["policy"].items()},summaries[f]["reach_count"])
def __file_as_path():
    from pathlib import Path
    return Path(__file__)
if __name__=="__main__":main()
