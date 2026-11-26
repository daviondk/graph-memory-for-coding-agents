"""Join annotated source titles after the ranking and the cache decisions are sealed."""
from collections import defaultdict
import numpy as np
from prepare import ROOT,PRIVATE,get,put,sha
from families import failures
def ci_paired(deltas):
    x=np.asarray(deltas,dtype=float);rng=np.random.default_rng(31404);avgs=[]
    for _ in range(100):
        avgs.extend(x[rng.integers(len(x),size=(100,len(x)))].mean(axis=1))
    return {"delta_pp":float(x.mean()),"ci95_pp":np.quantile(avgs,[.025,.975]).tolist(),"question_wins":int((x>1e-10).sum()),"question_losses":int((x< -1e-10).sum())}
def main():
    seal=get(ROOT/"measurement-seal.json");assert sha(ROOT/"cache-measurements.json.gz")==seal["measurements"]
    rankings=get(ROOT/"rankings.json.gz");cases=get(ROOT/"cache-measurements.json.gz")
    assert sha(PRIVATE/"labels.json.gz")==get(ROOT/"source.json")["labels"]
    labels=get(PRIVATE/"labels.json.gz");blind=get(PRIVATE/"blind.json.gz")
    stats=defaultdict(list);comparisons=defaultdict(list);quality=defaultdict(list);data={}
    events=defaultdict(int);missing=0
    for q,rec in rankings.items():
        perm=rec["order"];titles=[blind[q]["titles"][i] for i in perm];n=len(titles);refs=labels[q]["support"]
        gold={j for j,t in enumerate(titles) if t in refs};complete=len(gold)==len(refs)==2
        missing+=int(not complete);record={}
        for mode,arms in cases[q].items():
            pairs=rec["pairs"][mode];initial=tuple(pairs[0]);bm=(sum(1<<j for j in gold))
            counts=[int(complete and set(initial)==gold),len(gold&set(initial))/max(1,len(refs)),int(complete),0,0]
            mask=np.array([(1<<a)|(1<<b) for a,b in pairs]);bans=np.array([b for k,b in failures(n) if k==2])
            allowed=(mask[None,:]&bans[:,None])==0
            if complete:
                eligible=((bans&bm)==0);best=np.where(allowed.any(axis=1),allowed.argmax(axis=1),-1)
                rank=next(i for i,p in enumerate(pairs) if set(p)==gold)
                counts[3:]=[int((eligible&(best==rank)).sum()),int(eligible.sum())]
            quality[mode].append(counts);record[mode]=counts
            for ff,res in arms.items():
                f=int(ff);methods=res["stats"]
                for method,(size,by_size) in methods.items():
                    count=sum(v[0] for k,v in enumerate(by_size) if v and k<=f)
                    hit=sum(v[1] for k,v in enumerate(by_size) if v and k<=f)
                    exact=by_size[f]
                    if exact:stats[mode,f,method].append([size,100*hit/count,100*exact[1]/exact[0],exact[0],exact[1],exact[2],exact[3],count,hit])
                if methods["tree"][1][f]:
                    tx=methods["tree"][1][f]
                    for m in ("raw","raw_matched","doc_prefix","previous_plus_raw","linear"):
                        y=methods[m][1][f];comparisons[mode,f,m].append(100*(tx[1]-y[1])/tx[0])
                    events[mode,f]+=tx[0]
        data[q]=record
    aggregates={}
    for (mode,f,method),rows in stats.items():
        a=np.asarray(rows);s=a.sum(axis=0)
        aggregates.setdefault(mode,{}).setdefault(str(f),{})[method]={"nq":len(a),"mean_rows":a[:,0].mean(),"exact_up_to_f_pct":a[:,1].mean(),"exact_at_f_pct":a[:,2].mean(),"events_at_f":int(s[3]),"exact_events":int(s[4]),"wrong_nonempty":int(s[5]),"mean_scanned_at_f":s[6]/s[3],"events_up_to_f":int(s[7]),"exact_up_to_f":int(s[8])}
    paired={mode:{m:ci_paired(comparisons[mode,2,m]) for m in ("raw","raw_matched","doc_prefix","previous_plus_raw","linear")} for mode in ("add","joint")}
    gold_summary={}
    for mode,rows in quality.items():
        a=np.array(rows,dtype=float);v=a.sum(axis=0);eligible=a[:,4]>0
        gold_summary[mode]={"baseline_gold_exact_pct":100*a[:,0].mean(),"baseline_doc_recall_pct":100*a[:,1].mean(),"exact_initial":int(v[0]),"complete_gold_pair":int(v[2]),
           "two_bans_conditional_gold_exact_pct":100*np.mean(a[eligible,3]/a[eligible,4]),"eligible_questions":int(eligible.sum()),
           "events_gold_correct":int(v[3]),"events_both_gold_eligible":int(v[4])}
    put(ROOT/"annotated-outcomes.json.gz",data)
    out={"n":len(rankings),"without_two_matchable_titles":missing,"cache":aggregates,"primary_tree_minus":paired,
         "gold_docs":gold_summary,"measurements":seal["measurements"],"outcomes":sha(ROOT/"annotated-outcomes.json.gz")}
    put(ROOT/"results.json",out)
if __name__=="__main__":main()
