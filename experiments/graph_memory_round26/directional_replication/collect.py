from concurrent.futures import ProcessPoolExecutor
from collections import Counter
import hashlib,sys,os
os.environ["TOKENIZERS_PARALLELISM"]="false"
from rep_io import *
from cohort import body,qs,digest
sys.path.insert(0,str(R))
from dataset import squad_frags,Tokenizer,TOK
import direction
PAIRS=(("both","right"),("both","feasible_left"))
def parts(stage):
    return [D/f"{stage}-{i}.json.gz" for i in range(8)]
def worker(arg):
    i,stage=arg;tok=Tokenizer.from_file(str(TOK));cohort=read(D/"cohort.json.gz")["panel"]
    chosen={t:r for t,r in cohort.items() if int(digest(t)[:8],16)%8==i}
    data=read(TRAIN)["data"];out={}
    if stage=="read":
        name,h=read(D/"choices-lock.json")["files"][i];assert sha(D/name)==h
        prior=read(D/name);direction.PAIRS=PAIRS
    for a in data:
        t=a["title"]
        if t not in chosen:continue
        src=body(a);assert digest(src)==chosen[t]["body_sha"];ids=set(chosen[t]["ids"])
        if stage=="choices":
            items=sorted(((q,x) for q,x in qs(a) if q in ids),key=lambda z:z[0])
            assert len(items)==len(ids)
            for q,x,frags,fee in squad_frags(tok,src,items):
                cut=direction.choose(x,frags,{0:len(src)},tok);out[q]={"t":t,"before":fee,"base":[[e,l,l+len(s)] for e,l,s in frags],"cut":cut}
        else:
            for q in sorted(ids):
                r=prior.pop(q);assert r["t"]==t;out[q]=direction.execute(tok,r["cut"],src)
    if stage=="read":assert not prior
    f=parts(stage)[i];return [f.name,save(f,out)]
def main(stage):
    freeze();co=read(D/"cohort.json.gz");assert co["plan"]==sha(D/"plan.json") and co["source"]==sha(TRAIN)
    if stage=="read":assert read(D/"choices-lock.json")["cohort"]==sha(D/"cohort.json.gz")
    lock=D/f"{stage}-lock.json"
    if lock.exists():
        for n,h in read(lock)["files"]:assert sha(D/n)==h
        return
    with ProcessPoolExecutor(2) as ex:files=list(ex.map(worker,[(i,stage) for i in range(8)]))
    single=[q for n,h in files for q in read(D/n)]
    assert len(set(single))==len(single)==co["n"];assert set(single)=={q for v in co["panel"].values() for q in v["ids"]}
    save(lock,{"plan":sha(D/"plan.json"),"cohort":sha(D/"cohort.json.gz"),"code":sha(Path(__file__)),"unchanged_method":sha(R/"direction.py"),"same_initial_retriever":sha(R/"dataset.py"),"files":files,"n":len(single)})
if __name__=="__main__":main(sys.argv[1])
