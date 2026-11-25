import sys
from types import FunctionType
from collections import defaultdict
from statistics import mean
from shared25 import *
from dataset import c,Tokenizer,TOK,CACHE,ro,squad_rows
from direction import execute
from analyse import spans,trial,targets
import analyse
PAIRS2=(("both","right"),("both","feasible_left"))
def execute_comparisons(tok,cut,text):
    # The frozen billing function has exactly one contrast-list dependency.
    fn=FunctionType(execute.__code__,dict(execute.__globals__,PAIRS=PAIRS2))
    return fn(tok,cut,text)
def prepare(name,rows):
    old=read(D/f"{name}-opened.json.gz");tok=c.tok() if name=="mdd" else Tokenizer.from_file(str(TOK))
    out={}
    def one(q,cut,text):
        x=execute_comparisons(tok,cut,text)
        assert x["arms"]==old[q]["arms"];out[q]=x["equal"]
    if name=="ise":
        reg=ro(R/"read_causes/registry.sqlite");grp=defaultdict(list)
        for q,r in rows.items():grp[r["shard"],r["t"]].append((q,r))
        for (i,t),qq in grp.items():
            src=read(CACHE/f"{i}-{t}.json.gz")["fields"];ids=dict(reg.execute("select e,eid from address where t=?",(t,)))
            for q,r in qq:
                cut=r["cut"];one(q,cut,src[ids[cut["e"]]] if cut else "")
        reg.close()
    else:
        src={t:txt for t,txt,_ in squad_rows()} if name=="squad" else {i:d[2] for i,d in enumerate(c.get_views()["documents"])}
        for q,r in rows.items():
            cut=r["cut"];one(q,cut,src[r["t"] if name=="squad" else cut["e"]] if cut else "")
    h=save(D/f"{name}-secondary-cost.json.gz",out)
    save(D/f"{name}-secondary-seal.json",{"actions":h,"original":sha(D/f"{name}-open-seal.json"),"plan":sha(D/"SECONDARY_RU.md"),"code":sha(Path(__file__))})
def main(name):
    check();rows=read(D/f"{name}-choices.json.gz")
    seal=D/f"{name}-secondary-seal.json"
    if not seal.exists():prepare(name,rows)
    path=D/f"{name}-secondary-cost.json.gz";assert sha(path)==read(seal)["actions"]
    clips=read(path);outcomes=read(D/f"{name}-per-query.json.gz");gs=targets(name,rows);data=[];eq=defaultdict(list)
    for r in outcomes:
        q=r["q"];vis=spans(rows[q]["base"]);gold=[spans(z) for z in gs[q]]
        vec={}
        for x,y in PAIRS2:
            k=x+"-"+y;vec[k]=r["arms"][x]["fs"]-r["arms"][y]["fs"];a,b=(trial(vis,z,gold) for z in clips[q][k])
            assert a["tokens"]==b["tokens"]
            vec["equal/"+k]=a["fs"]-b["fs"];eq[k].append((a,b))
        data.append({"t":r["t"],"diff":vec})
    # The same clustered estimator, evaluated with the explicitly named follow-up comparisons.
    infer=FunctionType(analyse.inference.__code__,dict(analyse.inference.__globals__,PAIRS=PAIRS2))
    ret={"pairs":infer(data),"equal":{k:{"hits":[sum(p[j]["fs"] for p in v) for j in (0,1)],"average_tokens":mean(p[0]["tokens"] for p in v),"strictly_equal":len(v)} for k,v in eq.items()},"seal":sha(seal)}
    save(D/f"{name}-secondary.json",ret);print(name,ret)
if __name__=="__main__":main(sys.argv[1])
