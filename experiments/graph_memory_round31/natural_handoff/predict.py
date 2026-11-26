"""Write a bounded handoff from strictly previous observations, independent of successor evidence."""
from collections import Counter,defaultdict
from math import log
from time import perf_counter_ns
import re
from tokenizers import Tokenizer
from source import D,P,h,save,get,sha
T=__import__("pathlib").Path("D:/CodexResearch/x20-isetrace-runtime/inputs/tokenizer.json")
def terms(t):return re.findall(r"[a-z0-9]{2,}",re.sub(r"([a-z])([A-Z])",r"\1 \2",t).lower())
def main():
    pre=get(P/"prefix.json.gz");assert sha(P/"prefix.json.gz")==get(D/"projection.json")["prefix"]
    tokenizer=Tokenizer.from_file(str(T));tokenizer.no_truncation();timings=[];packets=[]
    for row in pre:
        start=perf_counter_ns();catalog={}
        for e in row["events"]:
            for ln,text in e["lines"]:
                k=(e["path"],ln,h(text));x=catalog.setdefault(k,dict(text=text,witness=set()));x["witness"].add(e["idx"])
        ks=sorted(catalog);n=len(ks);q=set(terms(row["question"]));docs=[Counter(terms(k[0]+" "+catalog[k]["text"])) for k in ks];df=Counter(t for doc in docs for t in doc);avg=sum(sum(doc.values()) for doc in docs)/max(1,n)
        bm=[]
        for doc in docs:
            length=sum(doc.values());bm.append(sum(log(1+(n-df[t]+.5)/(df[t]+.5))*(doc[t]*2.2)/(doc[t]+1.2*(.25+.75*length/max(1,avg))) for t in sorted(q&set(doc))))
        serial=["["+path+":"+str(ln)+"] "+catalog[path,ln,s]["text"] for path,ln,s in ks]
        lengths=[len(z.ids) for z in tokenizer.encode_batch(serial,add_special_tokens=False)] if serial else []
        order={}
        for a,signal in (("bm25",bm),("recent",[max(catalog[k]["witness"]) for k in ks]),("repeated",[len(catalog[k]["witness"]) for k in ks])):
            order[a]=sorted(range(n),key=lambda j:(-signal[j],ks[j]))
        rank={a:{k:i for i,k in enumerate(inds,1)} for a,inds in order.items()}
        for a,names in (("rrf2",["bm25","recent"]),("rrf3",["bm25","recent","repeated"])):
            order[a]=sorted(range(n),key=lambda j:(-sum(1/(60+rank[t][j]) for t in names),ks[j]))
        controls={}
        for a,inds in order.items():
            selected=[];cost=0
            for j in inds:
                if cost+lengths[j]<=512:selected.append(j);cost+=lengths[j]
            wire="\n".join(serial[i] for i in selected);assert len(tokenizer.encode(wire,add_special_tokens=False).ids)==cost<=512
            controls[a]=dict(index=[ks[i] for i in selected],tokens=cost,bytes=len(wire.encode()),wire_sha=h(wire))
        packets.append(dict(cp=row["cp"],issue=row["issue"],keys=ks,controls=controls))
        timings.append(perf_counter_ns()-start)
    save(D/"forecast-seal.json",dict(cases=len(packets),packets=save(P/"packets.json.gz",packets),code=sha(D/"predict.py"),inputs=sha(P/"prefix.json.gz"),tokenizer=sha(T),protocol=sha(D/"PROTOCOL_RU.md")))
    save(D/"producer-cost.json",dict(checkpoints=len(packets),sum_ns=sum(timings),per_checkpoint_ns=timings));print("sealed",len(packets))
if __name__=="__main__":main()

