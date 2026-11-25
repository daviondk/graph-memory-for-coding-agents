"""Evaluate the sealed open actions, with the former memory still visible."""
from collections import defaultdict,Counter
from statistics import mean,median
import os,sqlite3
os.environ["OPENBLAS_NUM_THREADS"]="1"
import numpy as np
from common import *
from novelty import union_intervals
ARMS=("first","bm25","first_positive","max_novelty","rank_novelty")

def combine(spans):
    by=defaultdict(list)
    for e,l,h in spans:
        if h>l:by[e].append((l,h))
    return {e:union_intervals(v) for e,v in by.items()}
def length(d):return sum(h-l for v in d.values() for l,h in v)
def intersects(a,b):
    return sum(max(0,min(r,h)-max(l,x)) for e,a1 in a.items() for l,r in a1 for x,h in b.get(e,()))
def paired(rows):
    pairs=[("rank_novelty","bm25"),("rank_novelty","first_positive"),("rank_novelty","max_novelty"),("rank_novelty","first"),("first_positive","bm25"),("max_novelty","bm25")]
    fields=("union_fs","union_coverage","added_source_chars","open_tokens")
    vecs=[(q,v["t"],[v["arms"][a][k]-v["arms"][b][k] for a,b in pairs for k in fields]) for q,v in sorted(rows.items())]
    groups=defaultdict(list)
    for q,t,v in vecs:groups[t].append(v)
    sizes=np.asarray([len(groups[t]) for t in sorted(groups)]);sums=np.asarray([np.sum(groups[t],axis=0) for t in sorted(groups)])
    assert len(sizes)==1207 and sizes.sum()==2000
    delta=sums.sum(axis=0)/2000;center=sums-sizes[:,None]*delta
    se=np.sqrt((center**2).sum(axis=0)*len(sizes)/(len(sizes)-1))/2000
    rng=np.random.default_rng(23625);boot=[];tmax=[];primary=[0,len(fields)]
    for _ in range(200):
        ix=rng.integers(0,len(sizes),size=(50,len(sizes)));boot.append(sums[ix].sum(axis=1)/sizes[ix].sum(axis=1)[:,None])
        signs=rng.choice((-1,1),size=(50,len(sizes)));z=(signs@center[:,primary])/2000
        tmax.extend(np.max(np.abs(z/np.where(se[primary]>0,se[primary],1)),axis=1))
    ci=np.quantile(np.vstack(boot),[.025,.975],axis=0);cut=np.quantile(tmax,.95)
    out={}
    for i,(a,b) in enumerate(pairs):
        d={}
        for j,k in enumerate(fields):
            m=i*len(fields)+j;d[k]={"delta":float(delta[m]),"cluster95":ci[:,m].tolist()}
            if m in primary:d[k]["simultaneous95"]=[float(delta[m]-cut*se[m]),float(delta[m]+cut*se[m])]
        dv=[x[2][i*len(fields)] for x in vecs]
        d["wins"]=int(sum(x>0 for x in dv));d["losses"]=int(sum(x<0 for x in dv));out[a+"-"+b]=d
    return out

def main():
    run=read(D/"opened-seal.json");decision=read(D/"choice-seal.json")
    assert sha(D/"choice-seal.json")==run["choice"] and decision["plan"]==sha(D/"plan.json")
    off=W/"graph_memory_round18/isetrace_official";gold=read(off/"gold-spans.json.gz")
    cohort={r["query_id"]:r for r in read(off/"cohort.json")}
    reg=sqlite3.connect((PARENT/"registry.sqlite").as_uri()+"?mode=ro&immutable=1",uri=True)
    add=defaultdict(dict)
    for t,e,eid,ptr in reg.execute("select t,e,eid,ptr from address"):add[t][eid,ptr]=e
    reg.close();out={};cost=[];truth_rows={}
    for i in range(8):
        entries=run["files"][i];p=D/entries[0];assert sha(p)==entries[1]
        forecasts=decision["parts"][i];ap=D/forecasts[0];assert sha(ap)==forecasts[1]
        acts={r["q"]:r for r in read(ap)}
        stamp=PARENT/f"receipts-{i}.json.gz";assert sha(stamp)==read(PARENT/"receipt-lock.json")["files"][stamp.name]
        receipts={r["q"]:r for r in read(stamp)}
        for r in read(p):
            q,t=r["q"],r["t"];a=acts.pop(q);rec=receipts.pop(q);assert q not in out and t==cohort[q]["trajectory_id"]==rec["t"]==a["t"]
            paid,bytes_,visible,wire=rec["arms"]["ratio/merged"]["paid"]["2048"]
            assert a["wire"]==wire and a["paid_in"]==paid<=2048
            gs=combine([(add[t][s["event_id"],s["json_pointer"]],s["char_start"],s["char_end"]) for s in gold[q]])
            initial=combine(visible);total=length(gs);old=intersects(initial,gs)
            arms={}
            for k in ARMS:
                op=r["open"][k];pick=a["picks"][k]
                assert (op is None)==(pick is None)
                if op is None:shown=[];read_tokens=0;expected=0;pred_frac=0.
                else:
                    e,l,h,read_tokens=op;assert (e,l)==tuple(pick[:2]) and any(f==e and a<=l<b for f,a,b in visible)
                    assert 0<=l<=h and 0<read_tokens<=256
                    shown=[(e,l,h)];expected=pick[6];pred_frac=expected/pick[7] if pick[7] else 0.
                new=combine(visible+shown);newchars=length(new)-length(initial)
                openchars=length(combine(shown));added=intersects(new,gs)-old
                assert 0<=added<=newchars<=openchars and paid+read_tokens<=2304
                arms[k]={"union_fs":int(old+added==total),"initial_fs":int(old==total),"union_coverage":(old+added)/total,"gold_gain_chars":added,
                         "added_source_chars":newchars,"returned_source_chars":openchars,"open_only_fs":int(intersects(combine(shown),gs)==total),
                         "open_tokens":read_tokens,"all_tokens":paid+read_tokens,"abstained":int(op is None),"issued_zero_new":int(op is not None and newchars==0),
                         "predicted_new_chars":expected,"predicted_fraction":pred_frac,"actual_fraction":newchars/openchars if openchars else 0.}
            assert set(arms)==set(ARMS)
            out[q]={"t":t,"mode":cohort[q]["memory_mode"],"start_coverage":old/total,"arms":arms}
            cost.append(a["cost_ns"])
        assert not acts and not receipts
    assert len(out)==len(gold)==2000 and set(out)==set(cohort)
    base={z["arms"]["first"]["initial_fs"] for z in out.values()};assert base=={0,1}
    n_initial=sum(z["arms"]["first"]["initial_fs"] for z in out.values());assert n_initial==1671
    totals={}
    for k in ARMS:
        vs=[z["arms"][k] for z in out.values()]
        totals[k]={f:mean(q[f] for q in vs) for f in ("union_coverage","gold_gain_chars","added_source_chars","open_tokens","all_tokens","predicted_fraction","actual_fraction")}
        totals[k].update(hits=sum(q["union_fs"] for q in vs),rescued=sum(q["union_fs"]-q["initial_fs"] for q in vs),
               single_hits=sum(q["open_only_fs"] for q in vs),issued=len(vs)-sum(q["abstained"] for q in vs),abstained=sum(q["abstained"] for q in vs),
               issued_zero_new=sum(q["issued_zero_new"] for q in vs),any_new_gold=sum(q["gold_gain_chars"]>0 for q in vs),max_read=max(q["open_tokens"] for q in vs))
    assert totals["bm25"]["hits"]==1689 and totals["first"]["hits"]==1671
    save(D/"per-query.json.gz",out)
    result={"n":2000,"trajectories":1207,"initial_hits":n_initial,"summary":totals,"paired":paired(out),"catalog":read(D/"visible-seal.json"),
            "timing_median_us":{"length_lookup":median(x[0] for x in cost)/1000,"visible_windows_bm25":median(x[1] for x in cost)/1000,
                                  "headers_all_novelty_policies_and_audit":median(x[2] for x in cost)/1000},
            "individual":sha(D/"per-query.json.gz"),"actions":sha(D/"opened-seal.json"),"gold":sha(off/"gold-spans.json.gz"),"code":sha(Path(__file__))}
    save(D/"results.json",result)
if __name__=="__main__":main()

