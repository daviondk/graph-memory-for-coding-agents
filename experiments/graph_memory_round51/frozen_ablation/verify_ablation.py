"""Independent numerical check from visible ranks, token arrays and decoded answers."""
from common import D,BASE,DATA,raw,digest,source
from verify import score
import hashlib
import math
import struct
import numpy as np


def key(ts):
    return hashlib.sha256(struct.pack(f"<{len(ts)}I",*ts)).hexdigest()


def main():
    model=raw(BASE/"model.json");pred=raw(D/"choices.json.gz");paired=raw(D/"contexts.json.gz")
    stored=raw(D/"outcomes.json.gz");stats=raw(D/"results.json");fresh=raw(D/"new-answers.json.gz");nprompts=raw(D/"new-prompts.json.gz")
    plan=raw(D/"plan.json")
    assert plan["model"]==digest(BASE/"model.json") and plan["protocol"]==digest(D/"PROTOCOL_RU.md")
    assert plan["selector"]==digest(D/"select_frozen.py")
    assert set(nprompts)==set(fresh) and all(key(v)==k for k,v in nprompts.items())
    receipt=raw(D/"answer-seal.json")
    assert receipt["n"]==len(fresh) and receipt["answers"]==digest(D/"new-answers.json.gz")
    assert raw(D/"grade-seal.json")["results"]==digest(D/"results.json")
    replay=raw(D/"replay.json");new_verified=set();assignments=0
    for p,(root,_) in DATA.items():
        _,earlier,mp,ma=source(p)
        oldp=raw(root/"prompts.json.gz");olda=raw(root/"answers.json.gz");oldp.update(mp);olda.update(ma)
        assert len(replay[p])==6 and all(olda[k]==out for k,out in replay[p].items())
        fullp={**oldp,**nprompts};fulla={**olda,**fresh}
        ranks=raw(root/"orders.json.gz");lex=raw(root/"lex-orders.json.gz");gold=raw(root/"gold.json.gz")
        tail=raw(root/"reader-boundaries.json")["tail"]
        assert not set(nprompts)&set(oldp)
        for filename, expected in plan["ranks"][p].items():
            assert digest(root/filename)==expected
        for q,r in ranks.items():
            row=pred[p][q];ctx=paired[p][q];old=earlier[q]
            acts=r["order"];assert row["edge"]==bool(r["edges"])

            for a in ("graph","hybrid","masked"):
                w=model[a if a!="masked" else "graph"]["coef"];x={}
                for j,i in enumerate(acts):
                    k=str(i);features=[r["scores"][k],1/(1+lex[q]["question_rank"][k]),1/(1+lex[q]["snippet_rank"][k]),
                                      1/(1+j),float(a!="masked" and i in r["edges"])]
                    x[i]=math.fsum(v*w/s for v,w,s in zip(features,w,model["scale"]))
                chosen=max(acts,key=x.get)
                i,k,L=ctx["refs"][a];assert row[a]==i==chosen and i!=r["seed"]
                old_cap=old["n" if p=="2wiki" else "cap"];old_by_id={j:prev for j,prev,_ in old["refs"].values()}
                dense_tokens=oldp[old["refs"]["dense"][1]]
                prefix=dense_tokens[:len(dense_tokens)-old_cap-len(tail)]
                ts=fullp[k];cap=ctx["cap"]
                assert ctx["original"]==old_cap and cap<=old_cap and len(ts)==L==len(prefix)+cap+len(tail)
                assert ts[:len(prefix)]==prefix and ts[-len(tail):]==tail and k==key(ts)
                if i in old_by_id:assert ts==prefix+oldp[old_by_id[i]][len(prefix):len(prefix)+cap]+tail
                if k in fresh:new_verified.add(k)
                if p=="hotpot":g=gold[q];refs=[g["answer"]];titles=g["titles"];support=set(g["support_titles"])
                else:refs,titles,sup=gold[q];support=set(sup)
                em,f1=score(fulla[k]["answer"],refs)
                rec=stored[p][q][a];seen={titles[r["seed"]],titles[i]}
                assert em==rec["em"] and abs(f1-rec["f1"])<1e-12 and rec["full"]==int(support<=seen)
                assert abs(rec["recall"]-len(support&seen)/len(support))<1e-12
                assignments+=1
            assert row["edge"] or ctx["refs"]["graph"]==ctx["refs"]["masked"]
        assert stats[p]["shortened"]=={q:[r["original"],r["cap"]] for q,r in paired[p].items() if r["cap"]<r["original"]}
        for group,s in stats[p]["strata"].items():
            ids=sorted(q for q,r in pred[p].items() if group=="all" or (group=="edge")==r["edge"])
            assert len(ids)==s["n"] and len({paired[p][q]["cluster"] for q in ids})==s["n"]
            for a,results in s["policies"].items():
                for m,v in results.items():assert abs(v-np.mean([stored[p][q][a][m] for q in ids]))<1e-12
            arr=[];bounds=[]
            for name,res in s["contrasts"].items():
                a,b=name.split("-");assert res["switches"]==sum(pred[p][q][a]!=pred[p][q][b] for q in ids)
                for m,v in res.items():
                    if m=="switches":continue
                    ds=np.array([stored[p][q][a][m]-stored[p][q][b][m] for q in ids])
                    assert abs(v["delta_pp"]-ds.mean()*100)<1e-10
                    assert v["gains"]==sum(ds>1e-12) and v["losses"]==sum(ds< -1e-12)
                    if "sign_flip" in v:
                        sf=v["sign_flip"];nz=np.abs(ds[np.abs(ds)>1e-12]);observed=abs(ds.sum());rng=np.random.default_rng(510272)
                        assert len(nz)>20 and sf["nonzero"]==len(nz)
                        extreme=0
                        for _ in range(1000):
                            signs=2*rng.integers(0,2,size=(1000,len(nz)),dtype=np.int8)-1
                            extreme+=sum(np.abs((signs*nz).sum(axis=1))>=observed-1e-12)
                        assert extreme==sf["extreme"] and abs(sf["two_sided_p"]-(extreme+1)/1000001)<1e-12
                    arr.append(ds);bounds.append(v["ci95_pp"])
            data=np.stack(arr,axis=1);rng=np.random.default_rng(510812);n=len(ids)
            boot=np.vstack([data[rng.integers(n,size=(50,n))].mean(axis=1) for _ in range(200)])
            assert np.allclose(np.quantile(boot,[.025,.975],axis=0).T*100,bounds,atol=1e-9)
    assert new_verified==set(fresh)
    print(f"Verified {assignments} actions, {len(fresh)} new exact prompts and 12 GPU replays, all strata, paired intervals and sign flips.")


if __name__=="__main__": main()
