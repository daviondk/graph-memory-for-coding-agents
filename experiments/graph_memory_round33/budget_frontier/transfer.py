"""Repeat the selected prefix and add a fixed-count head as an explanatory control."""
from frontier import *
from concurrent.futures import ProcessPoolExecutor
SEEDS=(13,17,29,37,41)
def route(ranks,cost,k,prefix_limit=256):
    head_len=min(len(ranks["frozen"]),len(prefix(ranks["frozen"],cost,prefix_limit))+1)
    def join(n):
        head=ranks["frozen"][:n];removed=set(head);return head+[i for i in ranks["cost"] if i not in removed]
    return {**ranks,"prefix":join(head_len),"fixed_count":join(k)}
def metrics(ns,truth):
    vals=[nm.pilot.span_metrics_under_token_budget(ns,truth,b) for b in B]
    c=[v.coverage for v in vals];mrr=nm.span_mrr(ns,truth)
    return [sum(c)/5,*c,vals[3].full_support,mrr,mrr]
def choose_k():
    dev=load(HERE/"dev-ranks.json.gz");gold=load(R19/"write_transfer/gold-spans.json.gz");sel=load(HERE/"selection.json")
    cal,hold=set(sel["cal_t"]),set(sel["hold_t"]);out={}
    for p in sources("dev"):
        for r in load(p):
            q=r["q"];nodes=[nm.pilot.RankedNodeRecord.model_validate(v) for v in r["rr"]];g=tuple(nm.pilot.SourceSpan.model_validate(v) for v in gold[q]);src=dev[q];orders={"frozen":src["a0"],"cost":src["a4"]};cost=[n.token_count for n in nodes]
            out[q]={"t":r["t"],"arms":{}}
            for k in (1,2,3,4,8):
                ix=route(orders,cost,k)["fixed_count"];out[q]["arms"][str(k)]=metrics(tuple(nodes[j] for j in ix),g)
    means={k:np.mean([r["arms"][str(k)] for r in out.values() if r["t"] in cal],axis=0).tolist() for k in (1,2,3,4,8)}
    chosen=max(means,key=lambda k:(round(means[k][0],12),-k))
    hold_coverage=np.mean([r["arms"][str(chosen)] for r in out.values() if r["t"] in hold],axis=0).tolist()
    save(HERE/"count-selection.json",{"k":chosen,"cal":{str(k):v for k,v in means.items()},"holdout_metrics":hold_coverage,"dev_split":sha(HERE/"selection.json"),"protocol":sha(HERE/"FOLLOWUP_RU.md")})
def prepare(i):
    fcases={r["q"]:r for r in load(REL/f"rep-ranks-{i}.json.gz")};ccases=load(BUDGET/f"transfer-ranks-{i}.json.gz");base=load(sources("test")[i]);sel=load(HERE/"selection.json");k=load(HERE/"count-selection.json")["k"]
    cf=load(BUDGET/"selection.json")["policy"];single=load(HERE/"test-ranks.json.gz")
    threshold=int(sel["policies"]["single_prefix"][0][6:]);out={}
    for r in base:
        q=r["q"];cost=[n["token_count"] for n in r["rr"]];by={}
        for s in SEEDS:
            orders={"frozen":single[q]["a0"],"cost":single[q]["a4"]} if s==13 else {"frozen":fcases[q]["orders"][str(s)]["global_role"],"cost":ccases[q][str(s)][cf]}
            by[str(s)]=route(orders,cost,k,threshold)
            if s==13:assert by[str(s)]["prefix"]==single[q]["prefix"+str(threshold)]
        out[q]=by
    p=HERE/f"repeat-ranks-{i}.json.gz";save(p,out);return p.name,sha(p)
def m_shard(i):
    base=load(sources("test")[i]);ranks=load(HERE/f"repeat-ranks-{i}.json.gz");gold=load(nm.OFF/"gold-spans.json.gz");out={};schedule=load(HERE/"selection.json")["policies"]["binary_by_budget"]
    for r in base:
        q=r["q"];ns=[nm.pilot.RankedNodeRecord.model_validate(v) for v in r["rr"]];truth=tuple(nm.pilot.SourceSpan.model_validate(v) for v in gold[q])
        out[q]={"t":r["t"],"seeds":{}}
        for s in SEEDS:
            vals={m:metrics(tuple(ns[j] for j in ix),truth) for m,ix in ranks[q][str(s)].items()}
            chosen=[vals["frozen" if a=="a0" else "cost"] for a in schedule];c=[v[i+1] for i,v in enumerate(chosen)]
            vals["binary"]=[sum(c)/5,*c,chosen[3][6],chosen[1][7],chosen[3][8]]
            out[q]["seeds"][str(s)]=vals
    p=HERE/f"repeat-outcomes-{i}.json.gz";save(p,out);return p.name,sha(p)
def main():
    choose_k()
    with ProcessPoolExecutor(2) as ex:parts=dict(ex.map(prepare,range(8)))
    save(HERE/"repeat-seal.json",{"parts":parts,"k":sha(HERE/"count-selection.json"),"protocol":sha(HERE/"FOLLOWUP_RU.md"),"script":sha(Path(__file__))})
    with ProcessPoolExecutor(2) as ex:rez=dict(ex.map(m_shard,range(8)))
    rows={}
    for p,h in rez.items():assert sha(HERE/p)==h;rows.update(load(HERE/p))
    assert len(rows)==2000;stats={}
    for label,seeds in [(str(s),[s]) for s in SEEDS]+[("extra4",SEEDS[1:]),("all5",SEEDS)]:
        av={q:{"t":r["t"],"arms":{m:np.mean([r["seeds"][str(s)][m] for s in seeds],axis=0).tolist() for m in ("frozen","cost","binary","prefix","fixed_count")}} for q,r in rows.items()}
        means={m:np.mean([r["arms"][m] for r in av.values()],axis=0).tolist() for m in ("frozen","cost","binary","prefix","fixed_count")}
        contrasts={}
        for a,b in [("prefix","cost"),("prefix","frozen"),("prefix","binary"),("prefix","fixed_count"),("binary","cost"),("fixed_count","cost")]:
            v=paired({q:{"t":r["t"],"arms":{"global":r["arms"][b],"candidate":r["arms"][a]}} for q,r in av.items()},"candidate")
            contrasts[a+" vs "+b]={k:v[k] for k in ("delta_pp","ci95_pp")}
        stats[label]={"means":means,"vs":contrasts}
    save(HERE/"repeat-results.json",{"stats":stats,"outcomes":rez,"seal":sha(HERE/"repeat-seal.json")})
if __name__=="__main__": main()
