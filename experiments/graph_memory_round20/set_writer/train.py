"""Fit linear priorities with question-level evidence sets on the old train sample alone."""
from collections import defaultdict
import hashlib
import json
import os
import re
from pathlib import Path
import sys
for s in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):os.environ[s]="1"
from scipy.special import logsumexp,expit
from scipy.optimize import minimize
import numpy as np
D=Path(__file__).resolve().parent;OLD=D.parents[1]/"graph_memory_round19"
sys.path.insert(0,str(OLD/"write_learned"))
from features import rows,tool_lookup,design,stream,save,load,sha
from train_write import RUN,RAW,pilot,adapt_isetrace_record,parse_isetrace_record
def train():
    prior=load(OLD/"write_learned/model.json");base=prior["arms"]["full"];w0=np.array(base["coefficients"])
    evidence=load(OLD/"write_learned/train-evidence.json.gz");sample=load(OLD/"write_learned/plan.json")
    ids=set(sample["selection"]);assert set(evidence)==ids
    tok=stream.Tokenizer.from_file(str(stream.TOKENIZER))
    groups=[];pattern=re.compile(rb'"session_id"\s*:\s*"(traj_[^"]+)"'); count=0; skipped=0; positive=[]
    for sn in range(8):
        with (RAW/f"trajectories-{sn:05d}.jsonl").open("rb") as f:
            for raw in f:
                m=pattern.search(raw);t=m.group(1).decode()
                if t not in ids:continue
                ids.remove(t);priorp=RUN/"projection/train"/(t+".json.gz");assert sha(priorp)==sample["train_projection_sha"][t]
                p=load(priorp);assert p["digest"]==hashlib.sha256(raw).hexdigest()==evidence[t]["raw_record"]
                tr=adapt_isetrace_record(parse_isetrace_record(json.loads(raw)),source_revision=pilot.RAW[1])
                fields={**{e.event_id:e.raw_arguments for e in tr.tool_calls},**{e.event_id:e.content for e in tr.tool_outputs}}
                ad,bl,_,_=stream.stream_blocks(fields,p["pool"],tok);cost=[v[3] for v in bl]
                if sum(cost)<=8192:skipped+=len(evidence[t]["q"]);continue
                z,names=rows(ad,bl,fields,tool_lookup(p["pool"]));x=(design(z,names,prior["tools"],True)-base["means"])/base["scale"]
                s=x@w0;ties=[stream.stable(eid) for eid,_ in ad]
                keep=stream.select(cost,[((-float(v),ties[b[0]]),) for b,v in zip(bl,s)],0,8192)
                threshold=min(s[j] for j in keep);order=np.argsort(abs(s-threshold),kind="stable");count+=1
                for q,coords in sorted(evidence[t]["q"].items()):
                    intervals=defaultdict(list)
                    for sp in coords:intervals[sp["event_id"],sp["json_pointer"]].append((sp["char_start"],sp["char_end"]))
                    pos=np.array([any(a<h and l<b for l,h in intervals.get(tuple(ad[e]),())) for e,a,b,c,n in bl]);assert np.any(pos)
                    neg=order[~pos[order]][:32];assert len(neg)
                    groups.append((x[pos],x[neg]));positive.append(int(pos.sum()))
    assert not ids
    coef={"frozen":w0.tolist()};diagnostics={}
    for version in ("mean","set"):
        def loss(w):
            val=0.;grad=np.zeros_like(w)
            for pos,neg in groups:
                ps=pos@w;ns=neg@w
                nbar=logsumexp(ns)-np.log(len(ns));ng=np.exp(ns-logsumexp(ns))@neg
                if version=="mean":pbar=ps.mean();pg=pos.mean(axis=0)
                else:pbar=-logsumexp(-ps)+np.log(len(ps));pg=np.exp(-ps-logsumexp(-ps))@pos
                margin=nbar-pbar;val+=np.logaddexp(0,margin);grad+=expit(margin)*(ng-pg)
            diff=w-w0
            return val/len(groups)+0.025*(diff@diff),grad/len(groups)+0.05*diff
        result=minimize(loss,w0,jac=True,method="L-BFGS-B",options={"maxiter":250,"ftol":1e-10});assert result.success,result.message
        coef[version]=result.x.tolist()
        diagnostics[version]={"iterations":result.nit,"loss":float(result.fun),"delta_norm":float(np.linalg.norm(result.x-w0))}
    save(D/"model.json",{"base":sha(OLD/"write_learned/model.json"),"coef":coef,"diagnostics":diagnostics,"binding_trajectories":count,
        "training_questions":len(groups),"nonbinding_questions":skipped,"mean_positive_blocks":np.mean(positive),
        "protocol":sha(D/"PROTOCOL_RU.md"),"code":sha(D/"train.py"),"labels":sha(OLD/"write_learned/train-evidence.json.gz")})
if __name__=="__main__":train()
