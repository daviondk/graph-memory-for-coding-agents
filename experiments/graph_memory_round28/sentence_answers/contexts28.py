"""Match both source operators exactly in the reader's vocabulary using a label-free input view."""
from functools import lru_cache
from pathlib import Path
import os,sys,time
D=Path(__file__).resolve().parent;W=D.parents[1];P=Path("D:/CodexResearch/x20-r28-squad-qa")
R26=W/"graph_memory_round26/directional_answers";R27=W/"graph_memory_round27/sentence_window";R25=W/"graph_memory_round25/directional_open"
sys.path.insert(0,str(R26));from prepare import read,save,sha,h,Tokenizer,WP,ENCT,WEIGHTS,wire
sys.path.insert(0,str(R27));from operators import Reader,bill,txt
ARMS=("both","boundary_window")
def convert(ops,source):
    parts=[];anchor=None
    for atom in ops:
        if atom[0]=="h":anchor=atom[1]
        elif atom[0]=="s":
            assert anchor is not None
            if atom[1]<atom[2]:parts.append([atom[1],atom[2],anchor])
            anchor=None
        elif atom[0]=="n":
            if anchor is not None:return None
        else:raise ValueError(atom)
    # Omit header-only variants: they do not represent an actual source read, and cannot be supplied to R26's parser.
    generated,_=wire(source,parts)
    return parts if generated=="".join(txt(p,source) for p in ops) else None
class Memo:
    def __init__(self,tok):
        self.encode=lru_cache(maxsize=384)(tok.encode)
def make(q,view,initial,old_reads,spans,ut,ct):
    title,query=view["qs"][q];src=view["docs"][title];r=initial[q]
    choices=Reader(src,spans[title],ut).block(query,r["base"],r["cut"])
    if choices is None:fn=lambda k,c:([],0)
    else:fn,_=choices
    p26=old_reads[q]["arms"]["both"]
    expected=[[z[1],z[2],z[4]] for z in p26];full=fn("both",256);assert convert(full[0],src)==expected
    # Every cap -> exact original R27 operator, no trimming or rewriting operator output.
    options={k:{} for k in ARMS};inspections=0
    for cap in range(256,-1,-1):
        for k in ARMS:
            ops,uncost=fn(k,cap);parts=convert(ops,src)
            if parts is None:continue
            wiretext,_=wire(src,parts);native=len(ct.encode(wiretext,add_special_tokens=False).ids)
            if native<=256 and native not in options[k]:
                options[k][native]=(parts,uncost,cap)
        inspections+=1
        if all(256 in m for m in options.values()):break
    n=max(set(options[ARMS[0]])&set(options[ARMS[1]]))
    base=[[a,b,a] for _,a,b in r["base"]];basefee=len(ct.encode(wire(src,base)[0],add_special_tokens=False).ids)
    results={}
    for k in ARMS:
        chosen,unc,cap=options[k][n]
        c,layout=wire(src,base+chosen);assert len(ct.encode(c,add_special_tokens=False).ids)==basefee+n
        results[k]=dict(extra=chosen,cap=cap,native=n,uncased=unc,wire_sha=h(c),wire_native=basefee+n)
    return dict(title=title,base=base,arms=results,caps_checked=inspections)
def main():
    src=Path("D:/CodexResearch/x20-r26-squad-qa/blind-input.json.gz");assert sha(src)==read(R26/"input-lock.json")["view"]
    readseal=read(R25/"squad-open-seal.json");choiceseal=read(R25/"squad-choice-seal.json")
    assert sha(R25/"squad-opened.json.gz")==readseal["actions"] and sha(R25/"squad-choices.json.gz")==choiceseal["actions"]
    assert sha(D/"sentence-index.json.gz")==read(D/"sentence-seal.json")["index"]
    lock=dict(plan=sha(D/"PROTOCOL_RU.md"),code=sha(Path(__file__)),view=sha(src),sentence=sha(D/"sentence-seal.json"),
              operators=sha(R27/"operators.py"),direction=sha(R25/"direction.py"),choice=sha(R25/"squad-choice-seal.json"),opened=sha(R25/"squad-open-seal.json"),
              old_forecast=sha(R26/"forecast-seal.json"),reader_sha=sha(R26/"infer.py"),model=sha(WEIGHTS),tokenizer=sha(ENCT),wp=sha(WP))
    assert lock["operators"]==read(R27/"operator-lock.json")["ops"] and lock["direction"]==read(R27/"operator-lock.json")["prior_rule"]
    save(D/"input-plan.json",lock)
    root=P/("contexts-"+sha(D/"input-plan.json"));root.mkdir(exist_ok=True)
    ut=Tokenizer.from_file(str(WP));ct=Tokenizer.from_file(str(ENCT))
    v=read(src);spans=read(D/"sentence-index.json.gz");ini=read(R25/"squad-choices.json.gz");old=read(R25/"squad-opened.json.gz")
    out={};start=time.monotonic()
    for q in sorted(ini,key=lambda q:h("r28-contexts/"+q)):
        fp=root/(q+".json")
        if not fp.exists():save(fp,make(q,v,ini,old,spans,Memo(ut),Memo(ct)))
        out[q]=read(fp)
        if len(out)%48==0:print(len(out),round(time.monotonic()-start,2),flush=True)
    assert len(out)==576 and len({r["title"] for r in out.values()})==48
    save(D/"contexts.json.gz",out);save(D/"context-seal.json",dict(plan=sha(D/"input-plan.json"),contexts=sha(D/"contexts.json.gz"),n=len(out)))
if __name__=="__main__":main()
