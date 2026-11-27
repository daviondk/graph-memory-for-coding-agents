"""Build a self-contained explorer from the measured SQLite records and Git events."""
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
R59=HERE.parent
sys.path.insert(0,str(R59/"reference_audit"))
from check_refs import inputs,selections,uleb
from bench import prepare

METHODS=("copy","compressed","eager","lazy")
SCOPES={"Original · dense":("original","B"),"Original · sparse":("original","long"),
        "Transfer · dense":("external","B"),"Transfer · sparse":("external","long")}
HORIZONS=(0,1,4,16,"full")


def load(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)


def details(stream,panel,case):
    ops,_=prepare(stream,panel)
    past_writes=[x for x in ops if x[0]=="w"]
    fence=len(past_writes)//2
    cut=next(i+1 for i,x in enumerate(ops) if x[0]=="w" and x[1]==fence-1)
    prefix=past_writes[:fence]
    members={k:x[3] for k,x in enumerate(prefix)}
    keep=selections(list(members.values()))["demand1024"]
    names={}
    for _,paths in stream:
        if len(paths)<=64:
            for p in paths:
                names.setdefault(p,len(names))
    by_id={v:k for k,v in names.items()}
    seen=set();i=0;result=[]
    for op in ops[cut:]:
        if op[0]=="w":
            continue
        anchor=op[1]
        all_selected=sorted(j for j in keep if anchor in members[j])
        newly=[j for j in all_selected if j not in seen]
        seen.update(newly)
        expected=case["demand1024/lazy"]["queries"][i][5]
        assert sum(len(uleb(members[j])) for j in newly)==expected
        # Capture a few real requests with evidence, as well as the initial request.
        if len(result)<5 and (i==0 or newly):
            result.append(dict(q=i+1,anchor=by_id.get(anchor,"Previously unseen path"),first=expected,
                source=[[j,prefix[j][2][:9],len(members[j]),len(uleb(members[j]))] for j in newly],
                warm=len(all_selected)-len(newly),rank=[[by_id[a],s] for a,s in op[4]]))
        i+=1
    return result


def make():
    base=load(R59/"references/runs.json.gz")["cases"]
    caches=load(R59/"lazy/runs.json.gz")
    rows={}
    for origin,panel,repo,stream in inputs():
        key="/".join((origin,panel,repo));case=base[key]
        l=caches["cases"][origin+"-"+panel+"/"+repo]
        assert caches["fields"][2:4]==["posting_bytes","body_bytes"]
        data={}
        for h in HORIZONS:
            rates={}
            for sel in ("demand1024","full"):
                by_arm={}
                for a in METHODS:
                    record=case[sel+"/"+a]
                    st=record["setup"];qs=record["queries"]
                    if h!="full":qs=qs[:h]
                    by_arm[a]=[st["write"],st["load"],st["receipt"],st["source"],sum(x[2] for x in qs),
                               sum(x[4] for x in qs),sum(x[5] for x in qs),st["source_calls"]+st["catalog_calls"]+sum(x[1]+x[3] for x in qs)]
                rates[sel]=by_arm
            lu={}
            for k in (1024,4096):
                lu[k]={}
                for policy in ("events","joint","postings","counts"):
                    q=l["reads"][f"B8-{policy}-{k}"]
                    if h!="full":q=q[:h]
                    lu[k][policy]=[sum(x[2] for x in q),sum(x[3] for x in q),
                                   sum(x[0]+x[1] for x in q)]
            rates["cache"]=lu
            rates["queries"]=len(q)
            data[str(h)]=rates
        rows[key]=dict(g=origin,w=panel,project=repo,metrics=data,head=l["git_head"],
                       rank=case["cold"]["ranking_sha"],fence=l["fence"],examples=details(stream,panel,case))
    c=load(R59/"reference_audit/results.json")["sql"]["counterexample"]
    return dict(scopes=SCOPES,rows=rows,counter=c,holdout=load(R59/"holdout/results.json")["sketch"])


def main():
    dest=HERE/"index.html"
    data=make()
    payload=json.dumps(data,separators=(",",":"),ensure_ascii=False).replace("<","\\u003c")
    html=(HERE/"template.html").read_text("utf8").replace("@@DATA@@",payload)
    dest.write_bytes(html.encode("utf8"))
    print(len(html.encode()),sha256(dest.read_bytes()).hexdigest())


if __name__=="__main__":
    main()
