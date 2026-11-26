"""Publish bounded directories and result fingerprints for every possible requested path."""
import sys
from pathlib import Path
from collections import defaultdict
from tokenizers import Tokenizer

D=Path(__file__).resolve().parent
PRIOR=D.parents[1]/"graph_memory_round31/natural_handoff"
sys.path.insert(0,str(PRIOR))
from source import P,sha,get,save,h
TOKEN=Path("D:/CodexResearch/x20-isetrace-runtime/inputs/tokenizer.json")
LIMIT=512
METHODS=("last","widest","roundrobin","one_wide","novel","full")
def pack(order, lengths, limit):
    chosen=[];cost=0
    for i in order:
        if cost+lengths[i]<=limit:
            cost+=lengths[i];chosen.append(i)
    return chosen,cost

def event_rows(e):
    return [(ln,h(text)) for ln,text in e["lines"]]

def stage(c,tok):
    events=[e for e in c["events"] if e["lines"]]
    nr=len(events)
    if not nr:return {"address_tokens":dict.fromkeys(METHODS,0),"routes":{},"raw_bytes":0,"unique_events":0}
    keys=[set((e["path"],ln,h(txt)) for ln,txt in e["lines"]) for e in events]
    lengths=[len(e["lines"]) for e in events]
    addresses=[f'{e["path"]}@{e["idx"]}[{e["lines"][0][0]}-{e["lines"][-1][0]}]' for e in events]
    def costs(items):return [len(z.ids) for z in tok.encode_batch(items,add_special_tokens=False)]
    price=costs(addresses)
    recent=sorted(range(nr),key=lambda i:-events[i]["idx"])
    wide=sorted(recent,key=lambda i:-lengths[i])
    def representatives(order):
        seen=set();first=[];rest=[]
        for i in order:
            path=events[i]["path"]
            if path in seen:rest.append(i)
            else:seen.add(path);first.append(i)
        return first,rest
    a,b=representatives(recent);table,_=representatives(wide)
    ordered={"last":recent,"widest":wide,"roundrobin":a+b,"one_wide":table,"full":recent}
    available=set(range(nr));covered=set();novel=[]
    while available:
        i=max(available,key=lambda j:(len(keys[j]-covered)/price[j],events[j]["idx"]))
        available.remove(i);covered.update(keys[i]);novel.append(i)
    ordered["novel"]=novel
    material=[];total_b=0
    for e in events:
        idx=e["idx"];lines=e["lines"];items=[f'[{e["path"]}:{ln}] {txt}' for ln,txt in lines]
        values=costs(items);total_b+=len("\n".join(items).encode());m=len(items)
        interleaved=[j for k in range((m+1)//2) for j in ((k,m-1-k) if k!=m-1-k else (k,))]
        got={}
        for label,order in [("forward",range(m)),("boundary",interleaved)]:
            sel,used=pack(order,values,LIMIT);assert len(tok.encode("\n".join(items[i] for i in sel),add_special_tokens=False).ids)==used
            got[label]=dict(keys=[[lines[j][0],h(lines[j][1])] for j in sel],tokens=used)
        material.append(got)
    # Each address points to the immutable snapshot of this particular historical observation.
    assert len(set(e["idx"] for e in events))==nr
    prices={};routes={}
    for name,order in ordered.items():
        chosen,cost=pack(order,price,LIMIT if name!="full" else sum(price))
        assert len(tok.encode("\n".join(addresses[i] for i in chosen),add_special_tokens=False).ids)==cost
        prices[name]=cost
        for path in sorted({events[i]["path"] for i in chosen}):
            best=max((i for i in chosen if events[i]["path"]==path),key=lambda i:(lengths[i],events[i]["idx"]))
            routes.setdefault(path,{})[name]=events[best]["idx"]
    return dict(address_tokens=prices,routes=routes,material={events[i]["idx"]:x for i,x in enumerate(material)},raw_bytes=total_b,unique_events=nr)
def main():
    prefix=P/"prefix.json.gz";assert sha(prefix)==get(PRIOR/"projection.json")["prefix"]
    tok=Tokenizer.from_file(str(TOKEN));tok.no_truncation();data=get(prefix)
    rows={x["cp"]:stage(x,tok) for x in data}
    issues=sorted({x["issue"] for x in data},key=lambda x:h("r32-split/"+x))
    assert len(issues)==37
    save(D/"split.json",{"dev":issues[:12],"test":issues[12:]})
    save(D/"seal.json",{"prefix":sha(prefix),"program":sha(Path(__file__)),"protocol":sha(D/"PROTOCOL_RU.md"),"tokenizer":sha(TOKEN),"split":sha(D/"split.json"),"packets":save(D/"packets.json.gz",rows)})
if __name__=="__main__":main()