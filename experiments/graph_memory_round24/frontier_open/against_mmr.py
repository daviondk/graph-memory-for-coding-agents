"""Pair the original MMR control with an address shift on the exact same chosen field."""
from collections import defaultdict
import runpy
import sqlite3
from routes import D,S,c,read,write,sha,TOK,Tokenizer,CACHE,trim,paid_open,union_intervals
from evaluate_frontier import test
P=D.parent/"marginal_mmr"
def runone(row,old,fields,tok):
    edge=row["actions"]["right_edge"]
    shifted=old
    if old:
        e,l,h,n=old
        runs=union_intervals([(a,b) for d,a,b in row["base"] if d==e])
        end=next(b for a,b in runs if a<=l<b)
        if end<len(fields[e]):shifted=paid_open(tok,fields[e],e,end)
    cap=min((edge[3] if edge else 0),(old[3] if old else 0))
    return {"edge":edge,"mmr":old,"mmr_shift":shifted,"edge_eq":trim(tok,fields,edge,cap),"mmr_eq":trim(tok,fields,old,cap)}
def predict():
    model={};meta={}
    for corpus,tag in (("isetrace","ise"),("multidoc","mdd")):
        up=D/f"actions-{corpus}.json.gz";other=P/f"{tag}-opened.json.gz";meta[corpus]=[sha(up),sha(other)]
        data=read(up);old=read(other);new={};assert set(data)==set(old)
        if tag=="ise":
            tok=Tokenizer.from_file(str(TOK))
            reg=sqlite3.connect((S/"read_causes/registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
            for i in range(8):
                groups=defaultdict(list)
                for r in read(S/f"read_causes/receipts-{i}.json.gz"):groups[r["t"]].append(r["q"])
                for t,qs in groups.items():
                    fields=read(CACHE/f"{i}-{t}.json.gz")["fields"]
                    literal={e:fields[eid] for e,eid in reg.execute("select e,eid from address where t=?",(t,))}
                    for q in qs:new[q]=runone(data[q],old[q]["arms"]["max_50"],literal,tok)
            reg.close()
        else:
            tok=c.tok();literal={i:r[2] for i,r in enumerate(c.get_views()["documents"])}
            for q in data:new[q]=runone(data[q],old[q]["arms"]["max_50"],literal,tok)
        model[corpus]=new
    write(D/"mmr-actions.json.gz",model)
    write(D/"mmr-actions-lock.json",{"protocol":sha(D/"MMR_COMPARISON_RU.md"),"inputs":meta,"actions":sha(D/"mmr-actions.json.gz")})
def evaluate():
    data=read(D/"mmr-actions.json.gz");assert sha(D/"mmr-actions.json.gz")==read(D/"mmr-actions-lock.json")["actions"]
    sc=runpy.run_path(str(S/"transfer/score.py"),run_name="md_labels");docs,_=sc["labels"](c.get_views());un=sc["union"];ov=sc["overlap"]
    gold=read(D.parents[1]/"graph_memory_round18/isetrace_official/gold-spans.json.gz")
    db=sqlite3.connect((S/"read_causes/registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    ids={(t,eid,ptr):e for t,e,eid,ptr in db.execute("select t,e,eid,ptr from address")};db.close()
    output={};results={}
    for corp,pred in data.items():
        source=read(D/f"actions-{corp}.json.gz");rows={}
        for q,actions in pred.items():
            s=source[q]
            if corp=="isetrace":
                group=s["t"];gt=un([(ids[group,v["event_id"],v["json_pointer"]],v["char_start"],v["char_end"]) for v in gold[q]])
            else:gt=un(docs[q][0]);group=gt[0][0]
            size=sum(h-l for e,l,h in gt);out={}
            for a,item in actions.items():
                e,l,h,n=item or (-1,0,0,0);mem=un(s["base"]+([[e,l,h]] if h>l else []));hits=ov(gt,mem)
                out[a]=[int(hits==size),hits/size,n]
            rows[q]={"g":group,"scores":out}
        vals=[rows[q] for q in sorted(rows)]
        comparisons={}
        for l,r in (("edge","mmr"),("edge_eq","mmr_eq"),("mmr_shift","mmr")):
            comparisons[l+"-"+r]=test([v["scores"][l][0]-v["scores"][r][0] for v in vals],[v["g"] for v in vals])
        summary={k:{"hits":sum(v["scores"][k][0] for v in vals),"tokens":sum(v["scores"][k][2] for v in vals)/len(vals)} for k in vals[0]["scores"]}
        assert summary["mmr"]["hits"]==(1695 if corp=="isetrace" else 455)
        assert all(v["scores"]["edge_eq"][2]==v["scores"]["mmr_eq"][2] for v in vals)
        results[corp]={"contrasts":comparisons,"summary":summary}
        output[corp]=rows
    write(D/"mmr-outcomes.json.gz",output);write(D/"mmr-results.json",{"results":results,"scores":sha(D/"mmr-outcomes.json.gz")})
    for k,v in results.items():print(k,v["summary"],{a:(s["wins"],s["losses"],s["p_signflip"]) for a,s in v["contrasts"].items()})
if __name__=="__main__":predict();evaluate()
