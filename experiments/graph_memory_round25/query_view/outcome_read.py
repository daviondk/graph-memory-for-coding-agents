"""Score changing questions after the exact and approximate top-window decisions are fixed."""
from collections import defaultdict
import runpy
import sqlite3
from make_fixture import D,DB,SOURCE,decode,read,write,sha,Tokenizer,TOK
from dataset import squad_rows
from routes import paid_open,CACHE,S

def predict():
    prev=read(D/"query-lock.json");assert sha(D/"decisions.json.gz")==prev["decisions"]
    conn=sqlite3.connect(DB.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    reg=sqlite3.connect((S/"read_causes/registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    squad={title:source for title,source,_q in squad_rows()}
    by_query={r["q"]:r for r in read(D/"decisions.json.gz")}
    # Previous question and first-order choices were sealed independently for all questions in R24/25.
    parent=S.parents[0]/"graph_memory_round24/frontier_open/actions-isetrace.json.gz";frozen=read(parent)
    files=read(S/"read_causes/receipt-lock.json")
    trace_shard={}
    for i in range(8):
        p=S/f"read_causes/receipts-{i}.json.gz";assert sha(p)==files["files"][p.name]
        for r in read(p):trace_shard[r["t"]]=i
    # SQuAD's previously selected right continuations are directly available.
    sp=SOURCE/"squad-opened.json.gz";assert sha(sp)==read(SOURCE/"squad-open-seal.json")["actions"]
    sq_prev=read(sp);tok=Tokenizer.from_file(str(TOK))
    outputs={"isetrace":{},"squad":{}}
    for sid,corpus,group,q0,vblob in conn.execute("select sid,corpus,context,q0,projected from snapshot"):
        view=decode(vblob);coords=[r["coords"] for r in view["rows"]]
        base=[x[:3] for x in coords]
        first=next(([e,edge] for e,l,h,edge,elig in coords if elig),None)
        if corpus=="isetrace":
            data=read(CACHE/f"{trace_shard[group]}-{group}.json.gz")["fields"]
            fields={e:data[eid] for e,eid in reg.execute("select e,eid from address where t=?",(group,))}
            old=frozen[q0]["actions"]["right_edge"]
        else:
            fields={0:squad[group]}
            op=sq_prev[q0]["arms"]["right"];old=op[0][:4] if op else None
        cache={}
        for q, in conn.execute("select q from future where sid=?",(sid,)):
            rec=by_query[q];assert rec["g"]==sid
            choices={"scan":rec["arms"]["scan"][1],"projected":rec["arms"]["projected"][1],
                     "old_question":old[:2] if old else None,"first":first}
            actions={}
            for m,p in choices.items():
                if p is None:actions[m]=None;continue
                e,pos=p
                if (e,pos) not in cache:cache[e,pos]=paid_open(tok,fields[e],e,pos)
                actions[m]=cache[e,pos]
            if old:assert actions["old_question"]==old
            outputs[corpus][q]={"t":group,"base":base,"actions":actions}
    conn.close();reg.close()
    write(D/"next-actions.json.gz",outputs)
    write(D/"next-lock.json",{"actions":sha(D/"next-actions.json.gz"),"previous":sha(D/"query-lock.json"),"plan":sha(D/"NEXT_READ_RU.md")})
def evaluate():
    a=read(D/"next-lock.json");assert sha(D/"next-actions.json.gz")==a["actions"]
    sc=runpy.run_path(str(SOURCE/"analyse.py"),run_name="label_read")
    out={};report={}
    for c,rows in read(D/"next-actions.json.gz").items():
        tgt=sc["targets"]("ise" if c=="isetrace" else "squad",rows)
        result={}
        for q,r in rows.items():
            gt=[sc["spans"](x) for x in tgt[q]];base=sc["spans"](r["base"]);v={}
            for name,act in {"base":None,**r["actions"]}.items():
                visible=sc["spans"](base+([act[:3]] if act else []))
                frac=max(sc["overlap"](visible,g)/sc["length"](g) for g in gt)
                v[name]=[int(frac==1),frac,act[3] if act else 0]
            result[q]={"t":r["t"],"outcomes":v}
        out[c]=result
        report[c]={"n":len(result),"metrics":{k:{"hits":sum(x["outcomes"][k][0] for x in result.values()),
              "coverage":sum(x["outcomes"][k][1] for x in result.values())/len(result),
              "tokens":sum(x["outcomes"][k][2] for x in result.values())/len(result)} for k in next(iter(result.values()))["outcomes"]}}
        dif=[x["outcomes"]["scan"][0]-x["outcomes"]["projected"][0] for x in result.values()]
        report[c].update(wins=dif.count(1),losses=dif.count(-1))
    write(D/"next-outcomes.json.gz",out);write(D/"next-results.json",{"summary":report,"outcomes":sha(D/"next-outcomes.json.gz"),"seal":sha(D/"next-lock.json")})
    print(report)
if __name__=="__main__":predict();evaluate()
