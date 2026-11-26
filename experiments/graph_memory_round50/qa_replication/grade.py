"""Open labels only after the answer seal. Also run the unmodified official eval entry point on each arm."""
from collections import Counter
from contextlib import redirect_stdout
from io import StringIO
import importlib.util,json,sys,zipfile
import numpy as np
from paths_repl import *
ARMS=["true","lex","sham47011"]
import grade47
grade47.ARMS=ARMS
grade47.SEEDS=[47011]
analyze=grade47.analyze
sys.path.insert(0,str(D))
from verify import clean,score

def main():
    check()
    lock=get(D/"answer-seal.json");assert lock["answers"]==sha(D/"answers.json.gz") and lock["input"]==sha(D/"input-seal.json")
    source=get(EXT/"official-source.json");assert source["evaluator"]==sha(DATA/"author_evaluate.py")=="7c09ee2ec98c7ecb57df79eb68dba22eb381ab58d50e730dfcefafb4dda31458"
    assert source["archive"]==sha(DATA/"data_ids.zip")
    # Official ujson calls only use JSON I/O. Supply the same interface from the standard library.
    sys.modules.setdefault("ujson",json)
    spec=importlib.util.spec_from_file_location("author_2wiki_v11",DATA/"author_evaluate.py");author=importlib.util.module_from_spec(spec);spec.loader.exec_module(author)
    panel=set(get(D/"panel.json")["order"])
    from stream_json import iter_array
    with zipfile.ZipFile(DATA/"data_ids.zip") as z:
        cases=[]
        with z.open("data_ids/train.json") as f:
            for count,r in enumerate(iter_array(f),1):
                if r["_id"] in panel:
                    cases.append(r)
        assert count==167454
        with z.open(source["members"]["id_aliases.json"]) as f:all_aliases={r["Q_id"]:r for raw in f if (r:=json.loads(raw))}
    visible=get(P/"visible.json.gz");ctx=get(D/"contexts.json.gz");answers=get(D/"answers.json.gz");delivered=get(P/"delivered.json.gz")
    assert sha(P/"delivered.json.gz")==get(D/"input-seal.json")["delivered"]
    assert {r["_id"] for r in cases}==set(ctx)==panel and len(cases)==640
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
    gp=P/"grade-cases.json";ap=P/"replication-aliases.jsonl";pp=P/"grade-pred.json"
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
    put(D/"outcomes.json.gz",rows);put(D/"gold.json.gz",gold)
    put(D/"results.json",dict(groups=summary,official=official,alias_extended_questions=expanded,source_context_equal=len(cases),
        mean_doc_recall=recall,clusters=len({r["cluster"] for r in rs}),input_mean=float(np.mean([v["refs"]["true"][2] for v in ctx.values()])),
        inputs_vary=sum(v["refs"]["true"][1]!=v["refs"]["lex"][1] for v in ctx.values()),outcomes=sha(D/"outcomes.json.gz"),
        answers=sha(D/"answer-seal.json"),gold=sha(D/"gold.json.gz"),code=sha(Path(__file__))))
    print(official,summary["all"]["contrasts"]["true-lex"]["pp"],flush=True)
if __name__=="__main__":main()
