"""Grade sealed policies against author labels and verify author controls on all 106 cases."""
from collections import Counter
import json
import statistics
import tarfile
import numpy as np
from source import ARC,HERE,METHODS,R54,R55,read,save,digest

def metrics(order,gold):
    pos=[i+1 for i,p in enumerate(order[:5]) if p in gold]
    return [len(pos)/len(gold),int(bool(pos)),1/min(pos) if pos else 0]

def gold_data(rows):
    gold={};original={}
    with tarfile.open(ARC,"r|zst") as arc:
        for m in arc:
            name=m.name.split("/")[-1].removesuffix("_details.jsonl")
            if name not in METHODS:continue
            arm=METHODS[name]
            original[arm]={}
            for r in map(json.loads,arc.extractfile(m)):
                q=r["sample_id"]
                if q not in rows:continue
                target=set(r["gold_files"])
                assert target and target==gold.setdefault(q,target)
                recall=r["metrics"]["Recall@5"]
                assert abs(metrics(r["top_files"],target)[0]-recall)<1e-8
                original[arm][q]=recall
    return {q:sorted(v) for q,v in gold.items()},original

def compare(part,a,b):
    if not part:return None
    d=np.array([r["metrics"][a][0]-r["metrics"][b][0] for r in part])
    _,ix=np.unique([r["repo"] for r in part],return_inverse=True)
    lengths=np.bincount(ix);sums=np.bincount(ix,weights=d);k=len(lengths)
    multiplicity=np.random.default_rng(56027).multinomial(k,[1/k]*k,size=20000)
    vals=multiplicity@sums/(multiplicity@lengths)
    return dict(n=len(part),repos=k,delta=float(d.mean()),ci=np.quantile(vals,[.025,.975]).tolist(),
                wins=int((d>1e-12).sum()),losses=int((d< -1e-12).sum()),ties=int((abs(d)<=1e-12).sum()),
                macro_repo=float((sums/lengths).mean()))

PRIMARY="role_embed4_local8"
PAIRS=[(PRIMARY,b) for b in ["role_embed4","role_embed4_g32","role_embed4_g64","role_embed4_pop","role_embed4_once",
                             "embed4","embed8","repomap","lexical","name","fusion","oko_mean","codenib_dense"]]
PAIRS += [("role_embed4","embed4"),("role_embed4","name"),("fusion_local8","fusion"),("fusion_local8","fusion_embed8"),
          ("fusion_local8","fusion_pop"),("fusion_local8","fusion_g64"),("fusion","embed4")]
PAIRS += [(f"raw_{m}_local8",m) for m in ("lexical","repomap","embed4")]
PAIRS += [(f"role_{m}_local8",f"role_{m}") for m in ("lexical","repomap")]

def summary(rows):
    keys=next(iter(rows))["metrics"]
    means={m:list(map(statistics.fmean,zip(*(r["metrics"][m] for r in rows)))) for m in keys}
    return {"n":len(rows),"means":means,"comparisons":{a+"__"+b:compare(rows,a,b) for a,b in PAIRS}}

def main():
    assert all(digest(HERE/n)==h for n,h in read(HERE/"prediction-seal.json").items())
    roster=read(HERE/"roster.json");runs=read(HERE/"predictions.json.gz")
    gold,original=gold_data(roster)
    all_paths=read(HERE/"community.json.gz");catalog=read(HERE/"catalog.json.gz")
    raw_community={m:statistics.fmean(metrics(d[m],gold[q])[0] for q,d in all_paths.items()) for m in next(iter(all_paths.values()))}
    raw_community["oko_mean"]=statistics.fmean(raw_community[f"oko{i}"] for i in (1,2,3))
    assert abs(raw_community["oko_mean"]-.408)<.00051 and abs(raw_community["codenib_dense"]-.399)<.00051
    old=read(R55/"ranks.json.gz")
    old_bases={r["base"] for r in old.values()};old_repos={r["repo"] for r in old.values()}
    assert not set(old)&set(runs)
    out={};graded={}
    for b in ("new","original"):
        by_q={}
        for q,r in runs.items():
            base=r["base"];assert set(gold[q])<=set(catalog[base])
            values={m:metrics(v,gold[q]) for m,v in r["ranked"][b].items()}
            values["oko_mean"]=list(map(statistics.fmean,zip(*(values[f"oko{i}"] for i in (1,2,3)))))
            if b=="original":
                assert all(abs(values[m][0]-original[m][q])<1e-8 for m in METHODS.values())
            by_q[q]=dict(repo=r["repo"],base=base,metrics=values)
        cases=list(by_q.values())
        result=summary(cases)
        for label,subset in (
            ("disjoint_base",[v for q,v in by_q.items() if v["base"] not in old_bases]),
            ("disjoint_repo",[v for q,v in by_q.items() if v["repo"] not in old_repos]),
            ("anchor_in_base",[v for q,v in by_q.items() if runs[q]["seen_anchor"]>0]),
            ("activated",[v for q,v in by_q.items() if runs[q]["evidence"][b]["changed"]])):
            if subset:
                result[label]={a+"__"+c:compare(subset,a,c) for a,c in [(PRIMARY,"role_embed4"),("fusion_local8","fusion"),("role_embed4","embed4")]}
            else:result[label]={}
        result["changed_top5"]={m:sum(r["ranked"][b][m]!=r["ranked"][b][c] for r in runs.values())
                    for m,c in [(PRIMARY,"role_embed4"),("role_embed4_g32","role_embed4"),("role_embed4_g64","role_embed4"),("fusion_local8","fusion")]}
        result["per_repo"]={repo:{m:statistics.fmean(v["metrics"][m][0] for v in cases if v["repo"]==repo)
            for m in (PRIMARY,"role_embed4","embed4","fusion","fusion_local8")} for repo in sorted({v["repo"] for v in cases})}
        out[b]=result;graded[b]=by_q
    from rank import is_test
    out["scope"]={"eligible_n":len(runs),"queries":len(roster),"repos":len({r["repo"] for r in runs.values()}),
      "base_overlap":len({r["base"] for r in runs.values()} & old_bases),
      "task_base_overlap":sum(r["base"] in old_bases for r in runs.values()),
      "repo_overlap":len({r["repo"] for r in runs.values()}&old_repos),"eligible_bases":len({r["base"] for r in runs.values()}),
      "same_task_ids":0,"previously_in_R54_sessions":len(set(runs)&set(read(R54/"decisions.json.gz"))),
      "classification_recall_ceiling":statistics.fmean(sum(map(is_test,gold[q]))/len(gold[q]) for q in runs),
      "anchor_present":sum(r["seen_anchor"]>0 for r in runs.values()),
      "mean_consulted":{m:statistics.fmean(r["consulted"][m] for r in runs.values()) for m in ("g32","g64","local8")}}
    out["raw106"]={m:statistics.fmean(vals.values()) for m,vals in original.items()}|raw_community
    save(HERE/"ground-truth.json.gz",gold);save(HERE/"graded.json.gz",graded);save(HERE/"results.json",out)
    print(out["scope"]); print({m:[round(x,4) for x in out["new"]["means"][m]] for m in (PRIMARY,"role_embed4","embed4","name","fusion","fusion_g64","fusion_local8","fusion_embed8","fusion_pop","oko_mean","codenib_dense")})
    print(out["new"]["comparisons"][PRIMARY+"__role_embed4"])
if __name__=="__main__":main()
