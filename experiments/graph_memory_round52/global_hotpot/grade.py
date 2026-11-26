"""Open Hotpot support only when the complete prediction seal verifies; CPU-only portable replay."""
from collections import Counter
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import unicodedata
import numpy as np

D=Path(__file__).resolve().parent
S=Path("D:/CodexResearch/x20-r52-directory-hotpot")
DEV=Path("D:/CodexResearch/x20-r52-wiki-directory")
VAL=Path("D:/CodexResearch/x20-r31-hotpot/validation.parquet")
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def save(p,v):
    b=(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def canonical(s):return unicodedata.normalize("NFC"," ".join(s.replace("_"," ").split()))
def register_grades(qids):
    import pyarrow.parquet as pq
    roster=read(D/"roster.json");assert sha(VAL)==roster["source"]
    # First benchmark annotation read in this pipeline, after choices and model hashes were verified.
    gold={};want=set()
    for batch in pq.ParquetFile(VAL).iter_batches(columns=["id","supporting_facts","type"]):
        for r in batch.to_pylist():
            q=r["id"]
            if q in qids:
                g=sorted({canonical(t) for t in r["supporting_facts"]["title"]})
                assert g;gold[q]=[r["type"],g];want.update(g)
    assert set(gold)==qids
    counts=Counter();n=0
    with (S/"titles.txt").open(encoding="utf8") as f:
        for line in f:
            n+=1;t=canonical(line.rstrip("\n").split("\t",1)[1])
            if t in want:counts[t]+=1
    assert n==5989847
    save(D/"gold.json.gz",gold)
    save(D/"coverage.json.gz",{"n":n,"titles":{t:counts[t] for t in sorted(want)},"directory_sha":sha(S/"titles.txt"),"decision":sha(D/"prediction-seal.json")})
    hashes={f:sha(DEV/f) for f in roster["inputs"]}
    assert hashes==roster["inputs"]
    mutables=["seed.tsv","second.tsv","questions.in","questions.json.gz","opened.json.gz","second.in"]
    parent_seal=read(D.parent/"global_policy/prediction-seal.json");base=read(D.parent/"global_titles/prediction-seal.json");src=read(D.parent/"global_titles/source.json");opening=read(D.parent/"global_titles/opening.json");lex=read(D.parent/"global_titles/lexicon.json")
    assert sha(DEV/"questions.json.gz")==src["questions"] and sha(DEV/"second.tsv")==base["raw_output"] and sha(DEV/"opened.json.gz")==opening["opened"]
    assert all(sha(DEV/n)==parent_seal["upstream_cache"][n] for n in ["questions.in","seed.tsv","second.in","second.tsv"])
    save(D/"directory-integrity.json",{"input_hashes_before_after":hashes,"prior_session_outputs":{f:sha(DEV/f) for f in mutables},"catalog_n":n})
def contrast(full,recall,groups,arms):
    pairs=[("primary_href",x) for x in ("coord_cautious","primary_text","href_first","free","coord_question_only","coord_explicit","learned_dev","primary_free")]+[("learned_dev","coord_cautious"),("learned_dev","href_first"),("href_first","text_first")]
    cols=[(a,b,m) for a,b in pairs for m in ("full","recall")]
    mat=np.column_stack([(full if m=="full" else recall)[:,arms.index(a)]-(full if m=="full" else recall)[:,arms.index(b)] for a,b,m in cols])
    _,gi=np.unique(groups,return_inverse=True);size=np.bincount(gi);g=len(size)
    sums=np.array([np.bincount(gi,weights=v,minlength=g) for v in mat.T]).T
    rng=np.random.default_rng(520117);B=10000;boot=np.empty((B,mat.shape[1]))
    for start in range(0,B,100):
        idx=rng.integers(0,g,size=(100,g));boot[start:start+100,:]=sums[idx].sum(axis=1)/size[idx].sum(axis=1)[:,None]
    lo,hi=np.quantile(boot,[.025,.975],axis=0);out={}
    for i,(a,b,m) in enumerate(cols):
        col=mat[:,i];out.setdefault(a+"-"+b,{})[m]=dict(delta_pp=float(100*col.mean()),ci95_pp=[float(lo[i]*100),float(hi[i]*100)],
            wins=int((col>1e-12).sum()),losses=int((col< -1e-12).sum()))
    return out
def evaluate(store=False):
    seal=read(D/"prediction-seal.json")
    assert all(sha(D/f)==h for f,h in seal["files"].items())
    pred=read(D/"predictions.json.gz");qs=sorted(pred);arms=seal["arms"]
    assert len(qs)==seal["n"]==1280 and len(arms)==10
    if store:register_grades(set(qs))
    names=read(D/"chosen-titles.json.gz");gold=read(D/"gold.json.gz");cov=read(D/"coverage.json.gz");assert cov["decision"]==sha(D/"prediction-seal.json") and set(qs)==set(gold)
    title=lambda i:canonical(names[str(i)][1])
    full=[];rec=[];groups=[];rowdata={};subsets={};coverage=[];seeds=[];reachable=[];support_n=0;covered_n=0
    for j,q in enumerate(qs):
        r=pred[q];typ,gs=gold[q];g=set(gs);s=title(r["seed"]);hh=[len({s,title(i)}&g) for i in r["choices"]]
        f=[int(v==len(g)) for v in hh];full.append(f);rec.append([v/len(g) for v in hh]);groups.append(r["seed"])
        nc=sum(cov["titles"][t]>0 for t in g);support_n+=len(g);covered_n+=nc
        coverage.append(nc==len(g));seeds.append(s in g);reachable.append(nc==len(g) and len(g-{s})<=1)
        keys=[typ,"direct" if r["direct_gate"][1] else "fallback","covered" if coverage[-1] else "coverage_gap","first_hit" if seeds[-1] else "first_miss"]
        for k in keys:subsets.setdefault(k,[]).append(j)
        rowdata[q]=dict(covered_support=nc,total_support=len(g),full=f,support_hits=hh,first_hit=s in g)
    a=np.asarray(full,dtype=float);b=np.asarray(rec);groups=np.asarray(groups);roster=read(D/"roster.json")
    def summ(idx):
        return dict(n=len(idx),complete={k:int(a[idx,i].sum()) for i,k in enumerate(arms)},
                    recall={k:float(b[idx,i].mean()) for i,k in enumerate(arms)})
    n=len(qs)
    obj=dict(n=n,arms=arms,policies=summ(list(range(n))),contrasts=contrast(a,b,groups,arms),subsets={k:summ(v) for k,v in subsets.items()},
          coverage=dict(fully_covered_questions=sum(coverage),missing_questions=n-sum(coverage),unique_requested=len(cov["titles"]),
              unique_present=sum(v>0 for v in cov["titles"].values()),all_support_occurrences=support_n,present_support_occurrences=covered_n,
              max_complete_with_actual_first=sum(reachable),first_hits=sum(seeds)),
          independent_first_clusters=len(np.unique(groups)),max_cluster=max(Counter(groups.tolist()).values()),routes=seal["routes"],
          roster=sha(D/"roster.json"),prediction=sha(D/"prediction-seal.json"),gold=sha(D/"gold.json.gz"),coverage_sha256=sha(D/"coverage.json.gz"))
    if store:save(D/"records.json.gz",rowdata);save(D/"results.json",obj)
    else:assert obj==read(D/"results.json") and rowdata==read(D/"records.json.gz")
    print(n,obj["independent_first_clusters"],obj["policies"]["complete"],obj["coverage"])
    for x in ("primary_href-coord_cautious","primary_href-primary_text","primary_href-href_first","primary_href-learned_dev"):
        print(x,obj["contrasts"][x]["full"])
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--grade",action="store_true")
    evaluate(p.parse_args().grade)
