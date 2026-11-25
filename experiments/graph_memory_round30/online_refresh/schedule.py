"""Make hard-budget online decisions without access to a later queue item."""
import bisect
from collections import defaultdict
import gzip,json,math,random,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;R29=HERE.parents[1]/"graph_memory_round29";NATIVE=R29/"native_revisions"
sys.path.insert(0,str(NATIVE))
from fetch import CACHE,checksum
from route import features
from prepare import hashkey
BUDGET=171
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def write(p,obj):
    b=json.dumps(obj,sort_keys=True,separators=(",",":")).encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def main():
    blind=read(CACHE.parent/"projected/blind.json.gz");routes=read(NATIVE/"route-seal.json")
    local=read(R29/"revision_reader/forecasts.json.gz");qs=sorted(local);train=sorted(set(blind)-set(qs));assert all(blind[q]["training"] for q in train)
    distributions={};native={}
    for q in sorted(blind):
        a,b,*_=features(blind[q]);native[q]={}
        for method,v in (("basic",a),("local",a+b)):
            fit=routes["fit"][method];native[q][method]=float(((np.asarray(v)-fit["mean"])/fit["sd"])@np.array(fit["beta"])+fit["intercept"])
    for method in ("basic","local"):
        distributions[method]=sorted((native[q][method],hashkey("online-refresh-tie/"+q)) for q in train)
    groups=defaultdict(list)
    for q in qs:groups[blind[q]["group"]].append(q)
    settings={"protocol":checksum(HERE/"PROTOCOL_RU.md"),"code":checksum(Path(__file__)),"prior":checksum(NATIVE/"route-seal.json"),"n":len(qs),"capacity":BUDGET}
    write(HERE/"plan.json",settings);runs=[]
    for family in ("shuffled","by_document"):
        for rep in range(32):
            rng=random.Random(30175+rep);order=qs.copy();rng.shuffle(order)
            if family=="by_document":
                gs=sorted(groups);rng.shuffle(gs);priority={g:i for i,g in enumerate(gs)};order.sort(key=lambda q:priority[blind[q]["group"]])
            coins=[rng.random() for _ in order]
            for model,scores in (("native",native),("local_reader",{q:local[q]["priority"] for q in qs})):
                for mode in ("random","fixed_basic","fixed_local","dynamic_basic","dynamic_local"):
                    left=BUDGET;accepted=[]
                    for i,q in enumerate(order):
                        count=len(order)-i
                        if left==0:break
                        if left==count:take=True
                        elif mode=="random":take=coins[i]<left/count
                        else:
                            rule,kind=mode.split("_");frac=left/count if rule=="dynamic" else BUDGET/len(order)
                            reference=distributions[kind]
                            ix=min(len(reference)-1,math.floor((1-frac)*len(reference)))
                            take=(scores[q][kind],hashkey("online-refresh-tie/"+q))>=reference[ix]
                        if take:accepted.append(q);left-=1
                    assert len(set(accepted))==BUDGET and left==0
                    runs.append([family,rep,model,mode,accepted])
    write(HERE/"decisions.json.gz",runs);write(HERE/"decision-seal.json",{"decisions":checksum(HERE/"decisions.json.gz"),"plan":checksum(HERE/"plan.json")})
if __name__=="__main__":main()
