"""Open labels only after the answer seal. Also run the unmodified official eval entry point on each arm."""
from collections import Counter
from contextlib import redirect_stdout
from io import StringIO
import importlib.util,json,sys,zipfile
import numpy as np
from paths50 import *
from grade47 import analyze
sys.path.insert(0,str(D50))
from verify import clean,score

def main():
    check50()
    lock=get(D50/"answer-seal.json");assert lock["answers"]==sha(D50/"answers.json.gz") and lock["input"]==sha(D50/"input-seal.json")
    source=get(D50/"official-source.json");assert source["evaluator"]==sha(P50/"author_evaluate.py")=="7c09ee2ec98c7ecb57df79eb68dba22eb381ab58d50e730dfcefafb4dda31458"
    assert source["archive"]==sha(P50/"data_ids.zip")
    # Official ujson calls only use JSON I/O. Supply the same interface from the standard library.
    sys.modules.setdefault("ujson",json)
    spec=importlib.util.spec_from_file_location("author_2wiki_v11",P50/"author_evaluate.py");author=importlib.util.module_from_spec(spec);spec.loader.exec_module(author)
    with zipfile.ZipFile(P50/"data_ids.zip") as z:
        orig=json.loads(z.read(source["members"]["dev.json"]))
        with z.open(source["members"]["id_aliases.json"]) as f:all_aliases={r["Q_id"]:r for raw in f if (r:=json.loads(raw))}
    visible=get(P50/"visible.json.gz");ctx=get(D50/"contexts.json.gz");answers=get(D50/"answers.json.gz");delivered=get(P50/"delivered.json.gz")
    assert sha(P50/"delivered.json.gz")==get(D50/"input-seal.json")["delivered"]
    panel=set(ctx);cases=[r for r in orig if r["_id"] in panel];assert {r["_id"] for r in cases}==panel and len(orig)==12576
    rows={};gold={};expanded=0
    for r in cases:
        q=r["_id"];v=ctx[q];quest,seen=visible[q]
        assert r["question"]==quest and [[i,title," ".join(parts)] for i,(title,parts) in enumerate(r["context"])]==seen
        truth={r["answer"]};alias=all_aliases.get(r["answer_id"],{})
        truth.update(alias.get("aliases",[]));truth.update(alias.get("demonyms",[]));truth=sorted(truth);expanded+=len(truth)>1
        support={t for t,number in r["supporting_facts"]};assert support
        titles=[t for t,body in r["context"]];h=lambda s:hexb(s.encode())
        gold[q]=[truth,[h(x) for x in titles],sorted(map(h,support))]
        arms={}
        for arm,(target,k,L) in v["refs"].items():
            ans=answers[k]["answer"];em,f1=score(ans,truth);m=dict(em=0.,f1=0.,prec=0.,recall=0.)
            author.update_answer(m,ans,truth);assert em==m["em"] and abs(f1-m["f1"])<1e-12
            found={titles[v["seed"]],titles[target]};recall=len(found&support)/len(support)
            present=any(" "+" ".join(clean(ref))+" " in " "+" ".join(clean(text))+" " for ref in truth if clean(ref) for text in delivered[k])
            arms[arm]=[em,f1,int(support<=found),int(present),recall,L,answers[k]["tokens"]]
        rows[q]=dict(cluster=v["cluster"],switch=v["switch"],kind=r["type"],hops=len(support),arms=arms)
    # Official CLI-equivalent aggregate, unmodified function, with only answer predictions supplied.
    write=lambda p,x:p.write_text(json.dumps(x,ensure_ascii=True),encoding="ascii")
    gp=P50/"grade-cases.json";ap=P50/"grade-aliases.jsonl";pp=P50/"grade-pred.json"
    write(gp,[{k:r[k] for k in ("_id","answer","answer_id")} for r in cases])
    with ap.open("w",encoding="ascii") as f:
        for q in sorted({r["answer_id"] for r in cases if r["answer_id"] in all_aliases}):f.write(json.dumps(all_aliases[q],ensure_ascii=True)+"\n")
    official={}
    for arm in ARMS:
        write(pp,dict(answer={q:answers[v["refs"][arm][1]]["answer"] for q,v in ctx.items()},sp={},evidence={}))
        cap=StringIO()
        with redirect_stdout(cap):author.eval(str(pp),str(gp),str(ap))
        out=cap.getvalue();official[arm]={k:v for k,v in json.loads(out[out.rfind("{"):]).items() if k in ("em","f1")}
        for j,k in enumerate(("em","f1")):assert round(sum(x["arms"][arm][j] for x in rows.values())*100/len(rows),2)==official[arm][k]
    rs=list(rows.values());groups={"all":rs,"switched":[x for x in rs if x["switch"]],"same":[x for x in rs if not x["switch"]]}
    for ty in sorted({x["kind"] for x in rs}):groups["type_"+ty]=[x for x in rs if x["kind"]==ty]
    summary={k:analyze(v) for k,v in groups.items()}
    recall={a:np.mean([x["arms"][a][4] for x in rs]).item() for a in ARMS}
    put(D50/"outcomes.json.gz",rows);put(D50/"gold.json.gz",gold)
    put(D50/"results.json",dict(groups=summary,official=official,alias_extended_questions=expanded,source_context_equal=len(cases),
        mean_doc_recall=recall,clusters=len({r["cluster"] for r in rs}),input_mean=float(np.mean([v["refs"]["true"][2] for v in ctx.values()])),
        inputs_vary=sum(v["refs"]["true"][1]!=v["refs"]["lex"][1] for v in ctx.values()),outcomes=sha(D50/"outcomes.json.gz"),
        answers=sha(D50/"answer-seal.json"),gold=sha(D50/"gold.json.gz"),code=sha(Path(__file__))))
    print(official,summary["all"]["contrasts"]["true-lex"]["pp"],flush=True)
if __name__=="__main__":main()
