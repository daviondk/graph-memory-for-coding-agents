"""Diagnose attainable source coverage for a frozen interface, with labels used only for the oracle."""
from collections import Counter,defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import runpy
import sqlite3
import sys
D=Path(__file__).resolve().parent;S=D.parents[1]/"graph_memory_round23"
sys.path.insert(0,str(S/"open_transfer"))
from run import c,merged,visible,paid_open
sys.path.insert(0,str(S/"read_causes"))
from project import CACHE, TOK, Tokenizer,read,write,sha

def ranges(items):
    result=defaultdict(list)
    for e,l,h in sorted(items):
        vec=result[e]
        if vec and l<=vec[-1][1]:vec[-1][1]=max(h,vec[-1][1])
        else:vec.append([l,h])
    return result

def missing_ranges(gold,shown):
    ans=[]
    for e,vec in gold.items():
        for l,h in vec:
            cur=l
            for a,b in shown.get(e,[]):
                if b<=cur:continue
                if a>=h:break
                if a>cur:ans.append((e,cur,min(a,h)))
                cur=max(cur,b)
                if cur>=h:break
            if cur<h:ans.append((e,cur,h))
    return ans

def case(parts,fields,truth,tok):
    shown=ranges(parts);miss=missing_ranges(ranges(truth),shown)
    if not miss:return {"base":1}
    target={x[0] for x in miss};r={"base":0,"missing_fields":len(target),"missing_chars":sum(h-l for _,l,h in miss)}
    if len(target)>1:return r
    e=next(iter(target));l=min(v[1] for v in miss);h=max(v[2] for v in miss)
    r["field_visible"]=int(e in shown)
    a=paid_open(tok,fields[e],e,l);r["gold_start_fits"]=int(a[2]>=h)
    if e in shown:
        options=[v for v in parts if v[0]==e]
        windows=visible(options,fields,tok)
        positions=sorted({w[1] for w in windows})
        # A forward-only read starting past the first missing character cannot succeed.
        feasible=[x for x in positions if x<=l]
        works=[]
        for start in feasible:
            if paid_open(tok,fields[e],e,start)[2]>=h:works.append(start)
        r.update(target_starts=len(positions),legal_successes=len(works),example=([e,works[0]] if works else None))
    return r

def isetrace():
    prev=S/"read_causes";gold=read(D.parents[1]/"graph_memory_round18/isetrace_official/gold-spans.json.gz")
    old=read(prev/"per-query.json.gz")["questions"];actual=read(S/"marginal_open/results.json");rows={}
    tok=Tokenizer.from_file(str(TOK))
    db=sqlite3.connect((prev/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    seal=read(prev/"receipt-lock.json")
    for i in range(8):
        path=prev/f"receipts-{i}.json.gz";assert sha(path)==seal["files"][path.name]
        grouped=defaultdict(list)
        for row in read(path):grouped[row["t"]].append(row)
        for t,series in grouped.items():
            fd=read(CACHE/f"{i}-{t}.json.gz")["fields"]
            codes={(eid,pt):e for e,eid,pt in db.execute("SELECT e,eid,ptr FROM address WHERE t=?",(t,))}
            fields={e:fd[eid] for (eid,pt),e in codes.items()}
            for row in series:
                q=row["q"];parts=row["arms"]["ratio/merged"]["paid"]["2048"][2]
                truth=[(codes[g["event_id"],g["json_pointer"]],g["char_start"],g["char_end"]) for g in gold[q]]
                result=case(parts,fields,truth,tok);assert result["base"]==old[q]["values"]["ratio/merged/2048"][0]
                rows[q]=dict(t=t,**result)
    db.close();return rows

def multidoc():
    ds=S/"transfer";v=c.get_views();tok=c.tok();docs={i:d[2] for i,d in enumerate(v["documents"])}
    labeler=runpy.run_path(str(ds/"score.py"),run_name="diagnostic_labels")
    gold,_=labeler["labels"](v);rows={}
    actions=read(S/"marginal_transfer/actions.json.gz")
    orig=read(S/"marginal_transfer/per-query.json.gz")["rows"]
    for q,record in actions.items():
        truth,reason=gold[q];assert not reason
        result=case(record["base"],docs,truth,tok);assert result["base"]==orig[q]["base"][0]
        rows[q]=dict(t=orig[q]["t"],**result)
    return rows

def main():
    data={"isetrace":isetrace(),"multidoc":multidoc()}
    summary={}
    for corpus,rows in data.items():
        counts=Counter()
        for r in rows.values():
            counts["n"]+=1;counts["base"]+=r["base"]
            if r["base"]:continue
            counts["incomplete"]+=1
            if r["missing_fields"]==1:
                counts["one_field_possible"]+=1
                counts["gold_start_any"]+=r["gold_start_fits"]
                if r["field_visible"]:
                    counts["one_visible_field_possible"]+=1
                    counts["gold_start_visible"]+=r["gold_start_fits"]
                    counts["legal_window"]+=int(r["legal_successes"]>0)
            else:counts["multi_field"]+=1
        assert counts["legal_window"]<=counts["one_visible_field_possible"]<=counts["one_field_possible"]<=counts["incomplete"]
        summary[corpus]=dict(counts)
    write(D/"per-query.json.gz",data);write(D/"results.json",{"summary":summary,"per_query":sha(D/"per-query.json.gz"),
       "code":sha(Path(__file__)),"protocol":sha(D/"PROTOCOL_RU.md"),"ise_forecast":sha(S/"read_causes/receipt-lock.json"),
       "external_forecast":sha(S/"marginal_transfer/forecast-seal.json")})
    print(summary)
if __name__=="__main__":main()
