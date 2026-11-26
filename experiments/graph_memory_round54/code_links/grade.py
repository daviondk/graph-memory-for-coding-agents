"""Unseal only after all addresses are frozen, and verify gold against the publication's row-level lists."""
from collections import defaultdict,Counter
import re,json
from sources import HERE,S,archive,save,load,hashfile,changed

def metric(rank,gold):
    rr=next((1/i for i,p in enumerate(rank,1) if p in gold),0.0)
    z={"mrr20":rr}
    for cut in (1,5,10,20):
        nh=len(set(rank[:cut])&gold)
        z["recall"+str(cut)]=nh/len(gold)
        z["hit"+str(cut)]=int(nh>0)
        if cut==5:z["complete5"]=int(nh==len(gold))
    return z
def collect(keys,forecasts):
    gold={};publisher={}
    with archive() as t:
        for m in t:
            if m.name=="./benchmark/v2_edit2ripple/samples.jsonl":
                for ln in t.extractfile(m):
                    r=json.loads(ln);q=r["id"]
                    if q in keys:
                        val=r["gold"]["files"]
                        gold[q]=set(val)
                        assert gold[q] and forecasts[q]["anchor"] not in gold[q]
            for name in ("bm25","repomap","lexical"):
                if m.name==f"./eval/v2_edit2ripple/{name}_details.jsonl":
                    ds={}
                    for line in t.extractfile(m):
                        r=json.loads(line);q=r["sample_id"]
                        if q not in keys:continue
                        assert r["top_files"]==forecasts[q]["published_raw"][name]
                        ds[q]=(set(r["gold_files"]),r["metrics"])
                    publisher[name]=ds
    for _,d in publisher.items():assert set(d)==keys and all(v[0]==gold[q] for q,v in d.items())
    return gold,publisher

def contrasts(rows,a,b):
    import numpy as np
    if not rows:return {}
    dif=np.array([r["graded"][a]["recall5"]-r["graded"][b]["recall5"] for r in rows])
    repos,ix=np.unique([r["repo"] for r in rows],return_inverse=True)
    weight=np.bincount(ix);by=np.bincount(ix,weights=dif)
    rng=np.random.default_rng(540131);sample=rng.integers(len(repos),size=(10000,len(repos)))
    values=by[sample].sum(1)/weight[sample].sum(1)
    return {"delta":float(dif.mean()),"ci95":np.quantile(values,[.025,.975]).tolist(),"wins":int((dif>0).sum()),
            "losses":int((dif<0).sum()),"tie":int((dif==0).sum()),"macro_repo":float((by/weight).mean()),
            "changed_top5":sum(set(r["top5"][a])!=set(r["top5"][b]) for r in rows)}
def summarize(rows,arms):
    if not rows:return {"n":0}
    measures={a:{k:sum(r["graded"][a][k] for r in rows)/len(rows) for k in rows[0]["graded"][a]} for a in arms}
    return {"n":len(rows),"repos":len({r["repo"] for r in rows}),"metrics":measures,
            "graph_minus_strong_text":contrasts(rows,"graph_vote","text_vote"),
            "graph_minus_bm25":contrasts(rows,"graph_vote","bm25"),
            "graph_minus_repomap":contrasts(rows,"graph_vote","repomap"),
            "graph_minus_lexical":contrasts(rows,"graph_vote","lexical"),
            "graph_minus_reverse":contrasts(rows,"graph_vote","reverse_vote")}
def main():
    seal=load(HERE/"prediction-seal.json");assert all(hashfile(HERE/k)==v for k,v in seal["files"].items())
    f=load(HERE/"forecasts.json.gz");qs=load(S/"actor-input.json.gz");arms=seal["arms"]
    assert set(f)==set(qs) and len(f)==seal["n"]
    g,pub=collect(set(f),f);rows={};publish=defaultdict(list);matches=Counter()
    for k,r in f.items():
        scores={m:metric(order,g[k]) for m,order in r["predictions"].items()}
        prompt=qs[k]["intent"]+"\n"+qs[k]["anchor_diff"]
        # Match the complete relative path as a standalone path, excluding a basename inside the given anchor path.
        direct=sorted(p for p in g[k] if re.search(r"(?<![\w./\\-])"+re.escape(p)+r"(?![\w./\\-])",prompt))
        rows[k]={"repo":r["repo"],"gold":sorted(g[k]),"graded":scores,
                 "top5":{a:order[:5] for a,order in r["predictions"].items()},"visible_full_gold_paths":direct}
        for m in ("bm25","repomap","lexical"):
            calc=metric(r["published_raw"][m],g[k]);published=pub[m][k][1]
            for field,mine in (("Recall@5","recall5"),("Recall@10","recall10"),("Recall@20","recall20"),("MRR","mrr20")):
                if field in published and isinstance(published[field],(int,float)):
                    # MRR may use a rank beyond the exported top 20; verify only if ranks fit for this metric.
                    if field=="MRR" and calc[mine]==0:continue
                    assert abs(float(published[field])-calc[mine])<1e-7,(k,m,field,published[field],calc[mine])
                    matches[m+":"+field]+=1
            publish[m].append(calc)
    allrows=list(rows.values());mainset=summarize(allrows,arms)
    more={"overall":mainset,"without_visible_gold_paths":summarize([r for r in allrows if not r["visible_full_gold_paths"]],arms),
          "per_repo":{repo:summarize([r for r in allrows if r["repo"]==repo],arms) for repo in sorted({r["repo"] for r in allrows})},
          "official_unmodified_subset":{m:{key:sum(v[key] for v in vals)/len(vals) for key in vals[0]} for m,vals in publish.items()},
          "published_metric_fields":sorted(next(iter(pub["bm25"].values()))[1]),"verified_published_metrics":matches,
          "scope_flags":dict(sum((Counter(r["edge_events"]) for r in f.values()),Counter())),
          "anchors_available":sum(r["anchor_exists"] for r in f.values()),
          "candidate_sizes":[min(r["pool_size"] for r in f.values()),max(r["pool_size"] for r in f.values())]}
    save(HERE/"graded-rows.json.gz",rows);save(HERE/"results.json",more)
    print("count",mainset["n"],"raw paths in question",sum(bool(r["visible_full_gold_paths"]) for r in allrows))
    print({a:round(vals["recall5"],4) for a,vals in mainset["metrics"].items()})
    print(mainset["graph_minus_strong_text"],mainset["graph_minus_bm25"],mainset["graph_minus_repomap"])
    print(more["published_metric_fields"])
if __name__=="__main__":main()

