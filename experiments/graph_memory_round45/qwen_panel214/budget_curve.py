"""Compute threshold for a complete evidence route and entire bounded-context recall curve."""
from common import *
from verify_metrics import scores
B=(512,1024,1536,2048,3072,4096,6144,8192,16384)
M=6144
def compute(g,rank):
    index={e:i for i,e in enumerate(g["ids"])};seq=[index[e] for e in rank];sizes=np.cumsum([g["cost"][e] for e in seq]).tolist()
    threshold=0 if scores([],g)[0] else next((s for n,s in enumerate(sizes,1) if scores(seq[:n],g)[0]),None)
    hit=[int(threshold is not None and threshold<=b) for b in B]
    use=[max([s for s in sizes if s<=b],default=0) for b in B]
    return dict(threshold=threshold,hit=hit,use=use,auc=max(0,1-threshold/M) if threshold is not None else 0)
def summarise(subset,data,repo):
    names=sorted(next(iter(data.values())));pairs=(("base/r39_no_observed_seen","base/qwen_seen"),("base/r39_no_observed","base/qwen"),
        ("fusion/r39_seen","base/qwen_seen"),("fusion/r39_seen","fusion/bge_seen"),("fusion/r39_seen","fusion/union_seen"))
    groups,pos=np.unique([repo[q] for q in subset],return_inverse=True);n=len(groups);cnt=np.bincount(pos)
    draws=np.random.default_rng(4021406).integers(n,size=(10000,n));w=np.stack([np.bincount(row,minlength=n) for row in draws]);tot=w@cnt
    methods={};contrasts={}
    for name in names:
        rec=[data[q][name] for q in subset];rs=np.array([r["hit"] for r in rec]);cost=np.array([r["use"] for r in rec])
        methods[name]=dict(counts=rs.sum(0).tolist(),mean_tokens=cost.mean(0).tolist(),auc=np.mean([r["auc"] for r in rec]))
    for a,b in pairs:
        ca=methods[a];cb=methods[b];v=np.array([data[q][a]["auc"]-data[q][b]["auc"] for q in subset])
        avg=np.bincount(pos,weights=v)/cnt
        contrasts[a+" minus "+b]=dict(delta=float(v.mean()),micro_ci=np.quantile((w@(avg*cnt))/tot,[.025,.975]).tolist(),
            macro=float(avg.mean()),macro_ci=np.quantile(w@avg/n,[.025,.975]).tolist(),
            wins=int(sum(v>0)),loss=int(sum(v<0)),at_caps=(np.array(ca["counts"])-cb["counts"]).tolist())
    return dict(states=len(subset),repos=n,methods=methods,contrasts=contrasts)
def main():
    assert sha(OUT/"BUDGET_AUDIT_RU.md")=="fe4078d5c492fc99b377b9a5db8dfb10a41e496f1bef179d90fb1a8a67686328"
    j=read(OUT/"cal-ordinal-judgments.json.gz");seal=read(OUT/"audit-seal.json");panel=read(OUT/"panel.json")
    assert sha(OUT/"cal-ordinal-judgments.json.gz")==seal["data"]
    data={q:{} for q in j}
    for prefix,n in (("","base"),("fusion-","fusion")):
        rank=read(OUT/(prefix+"predictions.json.gz"));o=read(OUT/(prefix+"outcomes.json.gz"))
        for q,methods in rank.items():
            for m,listing in methods.items():
                r=compute(j[q],listing);data[q][n+"/"+m]=r
                assert [r["hit"][B.index(b)] for b in (2048,6144)]==o[q]["arms"][m][2:4]
                assert [r["use"][B.index(b)] for b in (2048,6144)]==o[q]["tokens"][m][2:4]
    save("budget-thresholds.json.gz",data)
    panels={name:summarise(subset,data,panel["repo"]) for name,subset in (("outside204",panel["remaining"]),("all214",panel["order"]))}
    save("budget-results.json",dict(M=M,budgets=B,panels=panels,protocol=sha(OUT/"BUDGET_AUDIT_RU.md"),
         checks=sha(OUT/"audit-seal.json"),thresholds=sha(OUT/"budget-thresholds.json.gz")))
if __name__=="__main__":main()
