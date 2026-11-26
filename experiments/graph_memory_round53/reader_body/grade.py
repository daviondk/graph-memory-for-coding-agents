"""Official alias-aware EM/F1 and a paired reader/body interaction on the same 512 questions."""
from contextlib import redirect_stdout
from io import StringIO
import importlib.util
import numpy as np
from experiment import *

def main():
    seal=get("answer-seal.json")
    assert seal["answers"]==sha(D/"answers.json.gz") and seal["input"]==sha(D/"input-seal.json")
    inp=get("input-seal.json");assert inp["contexts"]==sha(D/"contexts.json.gz") and inp["prompts"]==sha(D/"prompts.json.gz")
    ctx=get("contexts.json.gz");answers=get("answers.json.gz")
    original=read(PREV/"records.json.gz");gold_seal=read(PREV/"grade-seal.json")
    assert sha(PREV/"records.json.gz")==gold_seal["records"] and sha(CACHE/"data_ids.zip")==gold_seal["gold"]
    assert sha(CACHE/"author_evaluate.py")==gold_seal["official"]
    sys.modules.setdefault("ujson",json)
    mod=importlib.util.spec_from_file_location("author_2wiki",CACHE/"author_evaluate.py");author=importlib.util.module_from_spec(mod);mod.loader.exec_module(author)
    sys.path.insert(0,str(EXP/"graph_memory_round50/adaptive_address"));from stream_json import iter_array
    with ZipFile(CACHE/"data_ids.zip") as z:
        with z.open("data_ids/train.json") as f:cases={r["_id"]:{k:r[k] for k in ("_id","answer","answer_id")} for r in iter_array(f) if r["_id"] in ctx}
        ids={v["answer_id"] for v in cases.values()}
        with z.open("data_ids/id_aliases.json") as f:aliases={r["Q_id"]:r for line in f if (r:=json.loads(line))["Q_id"] in ids}
    assert set(cases)==set(ctx)
    sys.path.insert(0,str(PREV));from grade_extra import sign_test
    records={};order=sorted(ctx)
    for q in order:
        g=cases[q];alts=aliases.get(g["answer_id"],{});refs={g["answer"],*alts.get("aliases",[]),*alts.get("demonyms",[])}
        row={}
        for arm in ARMS:
            out=dict(f1=0.,em=0.,prec=0.,recall=0.)
            author.update_answer(out,answers[ctx[q]["refs"][arm][1]]["answer"],refs)
            row[arm]=[out["f1"],out["em"]]
        records[q]=row
    from tempfile import TemporaryDirectory
    official={}
    with TemporaryDirectory(dir=D) as tmp:
        tmp=Path(tmp);gf=tmp/"gold.json";af=tmp/"aliases.jsonl";pf=tmp/"pred.json"
        dump=lambda path,x:path.write_text(json.dumps(x,ensure_ascii=True),encoding="ascii")
        dump(gf,list(cases.values()));af.write_text("".join(json.dumps(v,ensure_ascii=True)+"\n" for v in aliases.values()),encoding="ascii")
        for arm in ARMS:
            dump(pf,dict(answer={q:answers[ctx[q]["refs"][arm][1]]["answer"] for q in order},sp={},evidence={}))
            buf=StringIO()
            with redirect_stdout(buf):author.eval(str(pf),str(gf),str(af))
            txt=buf.getvalue();result=json.loads(txt[txt.rfind("{"):])
            ours=np.array([records[q][arm] for q in order]).mean(axis=0)*100
            assert abs(result["f1"]-ours[0])<=.005001 and abs(result["em"]-ours[1])<=.005001
            official[arm]=dict(f1=result["f1"],em=result["em"])
    matrix=np.array([[records[q][a] for a in ARMS] for q in order])
    real=np.array([[original["fallback|"+q][a][:2] for a in ARMS] for q in order])
    assert abs((real[:,0,0]-real[:,1,0]).mean()*100-2.56594114556)<1e-8
    swap_gap=matrix[:,0]-matrix[:,1]
    real_gap=real[:,0]-real[:,1]
    groups,ix=np.unique([ctx[q]["first"] for q in order],return_inverse=True);den=np.bincount(ix)
    rng=np.random.default_rng(532572);draw=rng.integers(len(groups),size=(10000,len(groups)))
    features=dict(real_gap=real_gap,donor_gap=swap_gap,interaction=real_gap-swap_gap,
        graph_real_minus_donor=real[:,0]-matrix[:,0],literal_real_minus_donor=real[:,1]-matrix[:,1])
    estimates={}
    for name,ar in features.items():
        summ={}
        for j,m in enumerate(("f1","em")):
            total=np.bincount(ix,weights=ar[:,j]);resampled=100*total[draw].sum(axis=1)/den[draw].sum(axis=1)
            z=dict(delta_pp=100*ar[:,j].mean(),ci95=list(np.quantile(resampled,[.025,.975])),
                   wins=int((ar[:,j]>1e-12).sum()),losses=int((ar[:,j]< -1e-12).sum()))
            if name in ("donor_gap","interaction") and m=="f1":z["signflip"]=sign_test(total)
            summ[m]=z
        estimates[name]=summ
    put("records.json.gz",records)
    result=dict(official=official,real=dict(zip(ARMS,(100*real.mean(axis=0)).tolist())),n=len(order),
        clusters=len(groups),unique=len(answers),discordant=sum(v["refs"][ARMS[0]][0]!=v["refs"][ARMS[1]][0] for v in ctx.values()),
        distinct_donors=len({v["donor"] for v in ctx.values()}),contrasts=estimates,metrics=["f1","em"])
    put("results.json",result)
    put("grade-seal.json",dict(results=sha(D/"results.json"),records=sha(D/"records.json.gz"),answers=sha(D/"answer-seal.json"),code=sha(Path(__file__)),
       author=gold_seal["official"],gold=gold_seal["gold"],original_records=gold_seal["records"]))
    print(json.dumps(result))
if __name__=="__main__":main()
