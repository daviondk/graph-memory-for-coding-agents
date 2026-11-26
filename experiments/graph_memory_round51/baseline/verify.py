"""Independently replay the archived ranking controls, decisions, QA scores and uncertainty."""
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import string
import numpy as np
from scipy.stats import binomtest

HERE = Path(__file__).resolve().parent
R50 = HERE.parents[1] / "graph_memory_round50"


def read(file):
    stream = gzip.open if file.suffix == ".gz" else open
    with stream(file, "rt", encoding="utf8") as handle:
        return json.load(handle)


def sha(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def norm(s):
    words = s.lower().translate(str.maketrans("", "", string.punctuation)).split()
    return " ".join(re.sub(r"\b(a|an|the)\b", " ", " ".join(words)).split())


def score(pred, aliases):
    pred = norm(pred)
    pred_count = Counter(pred.split())
    scores = []
    special = {"yes", "no", "noanswer"}
    for a in aliases:
        a = norm(a)
        same = int(a == pred)
        n = sum((pred_count & Counter(a.split())).values())
        f = (2*n/(len(pred.split())+len(a.split())) if n and
             (same or (a not in special and pred not in special)) else 0.0)
        scores.append((same, f))
    return max(v[0] for v in scores), max(v[1] for v in scores)


def close(x,y):
    assert math.isclose(x,y,rel_tol=1e-11,abs_tol=1e-11),(x,y)


def matrix(rank, lex):
    res = {}
    for j,idx in enumerate(rank["order"]):
        key = str(idx)
        res[idx] = [rank["scores"][key], 1/(lex["question_rank"][key]+1),
                    1/(lex["snippet_rank"][key]+1), 1/(j+1), int(idx in rank["edges"])]
    return res


def main():
    protocol = read(HERE/"registration.json")
    assert sha(HERE/"PROTOCOL_RU.md") == protocol["protocol"]
    for path, h in protocol["files"].items():
        assert sha(R50/path) == h
    decisions, ev, model, results = [read(HERE/f) for f in
        ("decisions.json.gz","records.json.gz","model.json","results.json")]
    lock = read(HERE/"decision-seal.json")
    for k,f in (("decisions","decisions.json.gz"),("model","model.json"),
                ("code","study.py"),("registration","registration.json")):
        assert lock[k] == sha(HERE/f)
    checked = 0
    clusters = set()
    for panel in ("semantic_address","adaptive_address","gate_confirmation"):
        root = R50/panel
        lex = read(R50/"qa_replication/orders.json.gz" if panel=="semantic_address" else root/"lex-orders.json.gz")
        rank,gold,ctx,ans,prompts = [read(root/f) for f in
            ("orders.json.gz","gold.json.gz","contexts.json.gz","answers.json.gz","prompts.json.gz")]
        ids = sorted(rank)
        mat = {q:matrix(rank[q],lex[q]) for q in ids}
        prior = set(clusters)
        clusters.update(x["cluster"] for x in ctx.values())
        assert len(clusters)-len(prior) == len(ctx)
        if panel=="semantic_address":
            points=np.array([v for q in ids for v in mat[q].values()])
            assert np.allclose(points.mean(0),model["mean"]) and np.allclose(points.std(0),model["scale"])
        for q in ids:
            for idx,raw_features in mat[q].items():
                mat[q][idx] = [(v-m)/s for v,m,s in zip(raw_features,model["mean"],model["scale"])]
        if panel=="semantic_address":
            for name in ("graph","hybrid"):
                coef=model[name]["coef"]; d=len(coef); grad=list(coef); pairs=0
                for q in ids:
                    _, titles, support = gold[q]
                    vec = mat[q]
                    pos = [vec[i] for i in vec if titles[i] in support]
                    neg = [vec[i] for i in vec if titles[i] not in support]
                    for a in pos:
                        for b in neg:
                            diff = [x-y for x,y in zip(a[:d],b[:d])]
                            z=math.fsum(i*j for i,j in zip(diff,coef))
                            w=1/((1+math.exp(z))*len(pos)*len(neg))
                            for j in range(d):
                                grad[j]-= w*diff[j]
                            pairs+=1
                assert pairs==model[name]["pairs"] and max(map(abs,grad))/len(ids)<1e-6
            xv,yv=[],[]
            for q in ids:
                a,b=rank[q]["dense"],rank[q]["linked_dense"]
                if a==b:continue
                target=[]
                for arm in ("dense","linked_dense"):
                    key=ctx[q]["refs"][arm][1]
                    target.append(score(ans[key]["answer"],gold[q][0])[1])
                xv.append([1]+[x-y for x,y in zip(mat[q][b][:4],mat[q][a][:4])])
                yv.append(target[1]-target[0])
            a=np.array(xv); coeff=np.r_[model["answer_gain"]["intercept"],model["answer_gain"]["coef"]]
            assert np.allclose(a.T@(a@coeff-yv)+np.r_[0,10*coeff[1:]],0,atol=1e-10)
            continue
        for q in ids:
            row=rank[q]; ords=row["order"]; a,b=row["dense"],row["linked_dense"]
            v=mat[q]; predicted={"dense":a,"linked":b,"gate":row["adaptive"]}
            for name in ("hybrid","graph"):
                coef=model[name]["coef"]
                val=lambda i:math.fsum(x*y for x,y in zip(v[i],coef))
                predicted[name]=max(ords,key=val)
                predicted[name+"_pair"]=max((a,b),key=val)
            gain=model["answer_gain"]["intercept"]+math.fsum(c*(x-y) for c,x,y in zip(model["answer_gain"]["coef"],v[b],v[a]))
            predicted["answer_pair"]=b if gain>0 else a
            assert predicted==decisions[panel][q]
            aliases,titles,goldtitles=gold[q]; n=ctx[q]["n"]
            tail=read(root/"reader-boundaries.json")["tail"] if q==ids[0] else tail
            known={}
            for i,k,L in ctx[q]["refs"].values():
                ts=prompts[k]; assert ts[-len(tail):]==tail and len(ts)==L
                prefix=ts[:L-n-len(tail)]
                known[i]=(k,prefix)
            assert len({tuple(e[1]) for e in known.values()})==1
            for name,i in predicted.items():
                rec=ev[panel][q][name]
                hits=set([titles[row["seed"]],titles[i]]) & set(goldtitles)
                assert rec["choice"]==i and rec["full"]==int(len(hits)==len(goldtitles))
                close(rec["recall"],len(hits)/len(goldtitles))
                if i in known:
                    k=known[i][0]; assert rec["prompt"]==k
                    em,f1=score(ans[k]["answer"],aliases);close(em,rec["em"]);close(f1,rec["f1"])
                else:
                    assert rec["f1"] is rec["em"] is rec["prompt"] is None
                checked+=1
        for name,r in results[panel]["policies"].items():
            series=[ev[panel][q][name] for q in ids]
            fs=[z["f1"] for z in series if z["f1"] is not None]
            n=len(series);assert n==r["n"] and len(fs)==r["covered"] and n-len(fs)==r["unknown"]
            close(r["full_support"],sum(x["full"] for x in series)/n)
            close(r["support_recall"],sum(x["recall"] for x in series)/n)
            close(r["switches"],sum(s["choice"]!=rank[q]["dense"] for q,s in zip(ids,series)))
            close(r["known_f1_sum"],sum(fs));close(r["known_em_sum"],sum(s["em"] or 0 for s in series))
            close(r["f1_range"][0],sum(fs)/n);close(r["f1_range"][1],(sum(fs)+n-len(fs))/n)
        cols=[]; lines=[]
        for pair,metrics in results[panel]["contrasts"].items():
            a,b=pair.split("-")
            for k,report in metrics.items():
                ds=[ev[panel][q][a][k]-ev[panel][q][b][k] for q in ids]
                close(report["delta_pp"],100*math.fsum(ds)/len(ids))
                pos=sum(x>1e-12 for x in ds);neg=sum(x< -1e-12 for x in ds)
                assert report["gains"]==pos and report["losses"]==neg
                if "mcnemar_exact_two_sided" in report:
                    close(report["mcnemar_exact_two_sided"],binomtest(pos,pos+neg).pvalue)
                cols.append(ds);lines.append(report["ci95_pp"])
        arr=np.asarray(cols).T
        rng=np.random.default_rng(510271);boot=[]
        for i in range(0,10000,50):
            boot.extend(arr[rng.integers(0,len(ids),size=(50,len(ids)))].mean(axis=1)*100)
        assert np.allclose(np.quantile(np.array(boot),[.025,.975],axis=0).T,lines,atol=1e-9)
    print(f"Verified 3 disjoint panels, rank and value fitting conditions, {checked} decisions, prompt-based regrading and all intervals.")


if __name__=="__main__":
    main()
