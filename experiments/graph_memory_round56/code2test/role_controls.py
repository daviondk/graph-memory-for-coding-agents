"""Cross-check the authors' full tests-only candidate reruns, then replace two sources of rank votes."""
from collections import Counter,defaultdict
import json
from pathlib import Path
from urllib.request import urlopen
import statistics
from source import HERE,read,save,digest
from rank import features,is_test,name_score,past_groups,temporal
from grade import metrics,compare

ORIGIN="https://raw.githubusercontent.com/eyuansu62/agent-retrieval-bench/9e4d68937f29d5967afd62f4f6a24c1478298133/data/eval/v1_1_candidate_filter_ablation/"
def collect():
    roster=read(HERE/"roster.json")
    candidates={q:{} for q in roster};references={};sources={}
    import hashlib
    for arm in ("lexical","repomap"):
        url=ORIGIN+arm+"_tests_only_details.jsonl"
        raw=urlopen(url,timeout=30).read()
        sources[arm]={"url":url,"sha256":hashlib.sha256(raw).hexdigest()}
        for r in map(json.loads,raw.splitlines()):
            q=r["sample_id"]
            if q not in roster:continue
            assert r["repo"]==roster[q]["repo"] and r["base_commit"]==roster[q]["base"]
            assert r["candidate_filter"]=="tests_only" and r["task_type"]=="code2test"
            candidates[q][arm]=r["top_files"]
            references.setdefault(q,{})[arm]=r["metrics"]["Recall@5"]
    assert all(set(r)=={"lexical","repomap"} for r in candidates.values())
    save(HERE/"role-author.json.gz",candidates)
    save(HERE/"role-author-reference.json.gz",references)
    save(HERE/"role-author-sources.json",sources)

def freeze():
    roster=read(HERE/"roster.json");catalog=read(HERE/"catalog.json.gz");hist=read(HERE/"histories.json.gz")
    author=read(HERE/"role-author.json.gz");dense=read(HERE/"publisher.json.gz")
    rec={}
    for q,r in roster.items():
        if not r["eligible"]:continue
        tests={p for p in catalog[r["base"]] if is_test(p)}
        anchors=set(r["anchors"])
        paths=[features(a) for a in anchors]
        names=sorted(tests,key=lambda p:(tuple(-v for v in name_score(p,paths)),p))
        groups=past_groups(hist[r["base"]]["history"],anchors,"local8")
        links,_=temporal(groups,anchors,tests,set())
        out={}
        for mode in ("new","original"):
            blocked=anchors if mode=="new" else set()
            def allowed(L):return [p for p in L if p not in blocked]
            auth={m:allowed(v) for m,v in author[q].items()}
            def fuse(extra):
                scores=Counter()
                lists=[allowed([p for p in dense[q]["embed4"] if p in tests]),auth["lexical"],auth["repomap"],allowed(names),extra]
                for seq in lists:
                    for i,p in enumerate(seq[:20],1):scores[p]+=1/(10+i)
                return sorted(scores,key=lambda p:(-scores[p],p))[:5]
            out[mode]={m:v[:5] for m,v in auth.items()}
            out[mode]["fusion"]=fuse([]);out[mode]["fusion_local8"]=fuse(links)
            out[mode]["fusion_embed8"]=fuse(allowed([p for p in dense[q]["embed8"] if p in tests]))
        rec[q]=out
    save(HERE/"role-ranks.json.gz",rec)
    save(HERE/"role-seal.json",{p:digest(HERE/p) for p in ("ROLE_CONTROLS_RU.md","role_controls.py","rank.py",
         "role-author.json.gz","role-author-sources.json","role-ranks.json.gz","prediction-seal.json")})

def grade():
    assert all(digest(HERE/n)==h for n,h in read(HERE/"role-seal.json").items())
    repo=read(HERE/"roster.json");ranks=read(HERE/"role-ranks.json.gz");gold=read(HERE/"ground-truth.json.gz")
    auth=read(HERE/"role-author.json.gz");reference=read(HERE/"role-author-reference.json.gz")
    prior=read(HERE/"graded.json.gz")
    for q,methods in auth.items():
        assert all(abs(metrics(v,gold[q])[0]-reference[q][m])<1e-8 for m,v in methods.items())
    out={"official106":{m:statistics.fmean(reference[q][m] for q in reference) for m in ("lexical","repomap")}}
    for b in ("new","original"):
        vals={}
        for q,record in ranks.items():
            vals[q]={"repo":repo[q]["repo"],"metrics":{m:metrics(v,gold[q]) for m,v in record[b].items()}}
            vals[q]["metrics"].update({"r56_primary":prior[b][q]["metrics"]["role_embed4_local8"],
                  "r56_fusion":prior[b][q]["metrics"]["fusion_local8"],"without_history":prior[b][q]["metrics"]["role_embed4"]})
        rows=list(vals.values())
        pairs=[(a,b) for a in ("r56_primary","r56_fusion") for b in ("lexical","repomap")]
        pairs+=[("fusion_local8","fusion"),("fusion_local8","fusion_embed8"),("fusion_embed8","fusion")]
        out[b]={"means":{m:list(map(statistics.fmean,zip(*(r["metrics"][m] for r in rows)))) for m in rows[0]["metrics"]},
                "contrasts":{a+"__"+b:compare(rows,a,b) for a,b in pairs}}
    save(HERE/"role-results.json",out)
    print({m:round(v[0],4) for m,v in out["new"]["means"].items()},out["official106"])
if __name__=="__main__":
    import sys
    {"collect":collect,"freeze":freeze,"grade":grade}[sys.argv[1]]()
