"""Use author v1.1 answer scoring and official aliases only after native generation is sealed."""
from prepare import *
from contextlib import redirect_stdout
from io import StringIO
import importlib.util,unicodedata
import numpy as np
R50=HERE.parents[2]/"graph_memory_round50"
DATA=Path("D:/CodexResearch/x20-r50-qa-external")
def canonical(s):return unicodedata.normalize("NFC"," ".join(s.replace("_"," ").split()))
def grade():
    answer_seal=load("answer-seal.json");contexts=load("contexts.json.gz");answers=load("answers.json.gz")
    assert hashfile(HERE/"answers.json.gz")==answer_seal["answers"]
    assert hashfile(HERE/"input-seal.json")==answer_seal["inputs"]
    input_seal=load("input-seal.json");assert input_seal["contexts"]==hashfile(HERE/"contexts.json.gz") and input_seal["prompts"]==hashfile(HERE/"prompts.json.gz")
    source=read(R50/"qa_external"/"official-source.json")
    assert hashfile(DATA/"author_evaluate.py")==source["evaluator"] and hashfile(DATA/"data_ids.zip")==source["archive"]
    sys.modules.setdefault("ujson",json)
    spec=importlib.util.spec_from_file_location("author_2wiki_v11",DATA/"author_evaluate.py")
    author=importlib.util.module_from_spec(spec);spec.loader.exec_module(author)
    sys.path.insert(0,str(R50/"adaptive_address"))
    from stream_json import iter_array
    with ZipFile(DATA/"data_ids.zip") as z:
        with z.open("data_ids/train.json") as f:cases={v["_id"]:v for v in iter_array(f) if v["_id"] in contexts}
        assert set(cases)==set(contexts)
        qa_ids={v["answer_id"] for v in cases.values()}
        with z.open(source["members"]["id_aliases.json"]) as f:aliases={r["Q_id"]:r for line in f if (r:=json.loads(line))["Q_id"] in qa_ids}
    titles=read(PARENT/"chosen-titles.json.gz")
    gp=RUN/"official-cases.json";ap=RUN/"official-aliases.jsonl"
    dump=lambda p,x:p.write_text(json.dumps(x,ensure_ascii=True),encoding="ascii")
    dump(gp,[{k:c[k] for k in ("_id","answer","answer_id")} for c in cases.values()])
    ap.write_text("".join(json.dumps(x,ensure_ascii=True)+"\n" for x in aliases.values()),encoding="ascii")
    metrics=("f1","em","full","recall");records={};orders=list(sorted(cases));expanded=0
    for q in orders:
        row=contexts[q];gold=cases[q];refs={gold["answer"]};entry=aliases.get(gold["answer_id"],{})
        refs.update(entry.get("aliases",[]));refs.update(entry.get("demonyms",[]));expanded+=len(refs)>1
        support=set(canonical(t) for t,_ in gold["supporting_facts"]);assert support
        by_arm={}
        for arm,(cid,k,_) in row["refs"].items():
            out=dict(f1=0.,em=0.,prec=0.,recall=0.);author.update_answer(out,answers[k]["answer"],refs)
            hit=len({canonical(titles[str(row["first"])][1]),canonical(titles[str(cid)][1])}&support)
            by_arm[arm]=[out["f1"],out["em"],int(hit==len(support)),hit/len(support)]
        records[q]=by_arm
    off={};policies={}
    for arm in ARMS:
        preds=RUN/("official-pred-"+arm+".json");dump(preds,dict(answer={q:answers[contexts[q]["refs"][arm][1]]["answer"] for q in orders},sp={},evidence={}))
        out=StringIO()
        with redirect_stdout(out):author.eval(str(preds),str(gp),str(ap))
        text=out.getvalue();scores=json.loads(text[text.rfind("{"):])
        a=np.array([records[q][arm] for q in orders])
        policies[arm]=dict(zip(metrics,(a.mean(axis=0)*100).tolist()),full_count=int(a[:,2].sum()))
        off[arm]={m:scores[m] for m in ("em","f1")}
        for m in ("em","f1"):assert abs(policies[arm][m]-off[arm][m])<=.005001
    seeds,ix=np.unique([contexts[q]["first"] for q in orders],return_inverse=True)
    den=np.bincount(ix);rng=np.random.default_rng(523842);draw=rng.integers(len(den),size=(10000,len(den)))
    comparisons={}
    for left,base in [(ARMS[0],a) for a in ARMS[1:]]+[("primary_href","primary_text")]:
        delta=np.array([np.array(records[q][left])-records[q][base] for q in orders])
        est={}
        for j,m in enumerate(metrics):
            DS=np.bincount(ix,weights=delta[:,j]);v=100*DS[draw].sum(axis=1)/den[draw].sum(axis=1)
            est[m]=dict(delta_pp=100*delta[:,j].mean(),ci95_pp=list(np.quantile(v,[.025,.975])),
                wins=int((delta[:,j]>1e-12).sum()),losses=int((delta[:,j]< -1e-12).sum()))
        est["changed_address"]=sum(contexts[q]["refs"][left][0]!=contexts[q]["refs"][base][0] for q in orders)
        comparisons[left+" vs "+base]=est
    result=dict(episodes=len(orders),unique_first=len(seeds),unique_prompts=len(answers),aliases_expanded=expanded,
        policies=policies,official=off,comparisons=comparisons,mean_first=np.mean([r["first_tokens"] for r in contexts.values()]),
        mean_second=np.mean([r["second_tokens"] for r in contexts.values()]),mean_visible=np.mean([r["refs"][ARMS[0]][2] for r in contexts.values()]))
    put("records.json.gz",records);put("results.json",result)
    put("grade-seal.json",dict(results=hashfile(HERE/"results.json"),records=hashfile(HERE/"records.json.gz"),
            answers=hashfile(HERE/"answer-seal.json"),author=source["evaluator"],gold_archive=source["archive"],code=hashfile(Path(__file__))))
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":grade()
