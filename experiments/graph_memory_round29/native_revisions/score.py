"""Score frozen refresh schedules and reproduce the benchmark authors' evaluator."""
import gzip,importlib.util,json
from collections import defaultdict
import numpy as np
from prepare import views,metrics
from fetch import ROOT,CACHE,FILES,read,save,checksum
def main():
    path=ROOT/"routes.json.gz";seal=json.loads((ROOT/"route-seal.json").read_bytes());assert checksum(path)==seal["routes"]
    routes=json.loads(gzip.decompress(path.read_bytes()))
    original,edits=views("original"),views("edits");old,updated=read("before"),read("after")
    saved_eval=CACHE/FILES["evaluation"]
    assert checksum(saved_eval)==json.loads((ROOT/"sources.json").read_bytes())["evaluation"]["sha"]
    spec=importlib.util.spec_from_file_location("ropes_official",saved_eval);official=importlib.util.module_from_spec(spec);spec.loader.exec_module(official)
    full=official.evaluate_contrast(read("original")["data"],old,read("edits")["data"],updated)
    def observations(q,answer):
        old_m=metrics(old[q],original[q][1]);f1,em=metrics(answer,edits[q][1])
        assert abs(official.metric_max_over_ground_truths(official.f1_score,answer,edits[q][1])-f1)<1e-9
        assert official.metric_max_over_ground_truths(official.exact_match_score,answer,edits[q][1])==em
        return [f1,em,int(old_m[1] and em)]
    direct_all=np.mean([observations(q,updated[q]) for q in edits],axis=0)
    assert np.allclose(direct_all,[full[k] for k in ("contrast_f1","contrast_exact_match","consistency")])
    cases={q:{"group":r["group"],"cold":observations(q,updated[q]),"old":observations(q,old[q]),
              "patch":observations(q,r["patch"]),"fresh_answer_changed":old[q]!=updated[q],"edit":r["different_fields"]} for q,r in routes.items()}
    qs=sorted(cases);N=len(qs);groups=sorted({r["group"] for r in routes.values()})
    membership=np.asarray([[cases[q]["group"]==g for q in qs] for g in groups],dtype=float);sizes=membership.sum(axis=1)
    draws=np.random.default_rng(293330).integers(len(groups),size=(20000,len(groups)))
    coverage=[0,N//10,N//3,N//2,N];results={}
    for n in coverage:
        arr={}
        for method in next(iter(routes.values()))["rank"]:
            arr[method]=np.array([cases[q]["cold" if routes[q]["rank"][method]<n else "old"] for q in qs])
        report={"mean":{m:(100*y.mean(axis=0)).tolist() for m,y in arr.items()},"local_minus":{}}
        for base in ("basic","missing","random","size"):
            diff=100*(arr["local"][:,0]-arr[base][:,0]);summed=membership@diff
            boot=summed[draws].sum(axis=1)/sizes[draws].sum(axis=1)
            report["local_minus"][base]={"pp":float(diff.mean()),"ci95":np.quantile(boot,[.025,.975]).tolist(),
                               "wins":int((diff>0).sum()),"losses":int((diff<0).sum())}
        results[str(n)]=report
    changed=[q for q in qs if routes[q]["patch_changed"]]
    variants={"patch":100*np.mean([v["patch"] for v in cases.values()],axis=0)}
    out={"heldout":N,"clusters":len(groups),"native_full_974":full,"scheduled":results,"metrics":["F1","EM","both_EM"],
         "patch_changed":len(changed),"patch_f1_wins":sum(cases[q]["patch"][0]>cases[q]["old"][0] for q in changed),
         "patch_f1_losses":sum(cases[q]["patch"][0]<cases[q]["old"][0] for q in changed),
         "patch":variants["patch"].tolist(),"refresh_vs_old_wins":sum(v["cold"][0]>v["old"][0] for v in cases.values()),
         "refresh_vs_old_losses":sum(v["cold"][0]<v["old"][0] for v in cases.values()),
         "native_answer_changed":sum(v["fresh_answer_changed"] for v in cases.values()),"routes":seal["routes"]}
    (ROOT/"outcomes.json.gz").write_bytes(gzip.compress(json.dumps(cases,sort_keys=True).encode(),mtime=0));out["outcomes"]=checksum(ROOT/"outcomes.json.gz")
    save("results.json",out)
if __name__=="__main__":main()
