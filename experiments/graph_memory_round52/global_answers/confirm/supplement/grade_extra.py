"""Grade a matched reserve-edge pair, and recover the exact contrast over the disjoint pool."""
from prepare_extra import *
import numpy as np
from contextlib import redirect_stdout
from io import StringIO
import importlib.util
sys.path.insert(0,str(D.parents[1]))
from signflip import subsets
R50=D.parents[3]/"graph_memory_round50"
DATA=Path("D:/CodexResearch/x20-r50-qa-external")
def sign_test(values):
    x=np.array([v for v in values if abs(v)>1e-12]);obs=abs(sum(x));n=len(x);eps=1e-10
    if obs<eps:return dict(p=1.,n=n)
    if n<=40:
        a=subsets(x[:n//2]);b=np.sort(subsets(x[n//2:]))
        cnt=int(np.searchsorted(b,-obs-a+eps,side="right").sum()+(len(b)-np.searchsorted(b,obs-a-eps,side="left")).sum())
        return dict(p=cnt/(2**n),n=n,draws=2**n,extreme=cnt)
    rng=np.random.default_rng(523899);cnt=0
    for _ in range(1000):
        z=rng.integers(0,2,size=(1000,n),dtype=np.int8)*2-1
        cnt+=int((np.abs((z*x).sum(axis=1))>=obs-eps).sum())
    return dict(p=(cnt+1)/1000001,n=n,draws=1000000,extreme=cnt)
def grade():
    import unicodedata
    canon=lambda t:unicodedata.normalize("NFC"," ".join(t.replace("_"," ").split()))
    goldsrc=read(R50/"qa_external/official-source.json");ctx=get("contexts.json.gz");ans=get("answers.json.gz");sel=get("choices.json.gz")
    assert get("answer-seal.json")["answers"]==hashfile(D/"answers.json.gz") and get("answer-seal.json")["inputs"]==hashfile(D/"input-seal.json")
    assert get("input-seal.json")["contexts"]==hashfile(D/"contexts.json.gz") and get("registration.json")["choices"]==hashfile(D/"choices.json.gz")
    assert hashfile(DATA/"author_evaluate.py")==goldsrc["evaluator"] and hashfile(DATA/"data_ids.zip")==goldsrc["archive"]
    sys.modules.setdefault("ujson",json)
    sp=importlib.util.spec_from_file_location("author_2wiki_v11",DATA/"author_evaluate.py");author=importlib.util.module_from_spec(sp);sp.loader.exec_module(author)
    sys.path.insert(0,str(R50/"adaptive_address"));from stream_json import iter_array
    qids={v["q"] for v in ctx.values()}
    with ZipFile(DATA/"data_ids.zip") as z:
        with z.open("data_ids/train.json") as f:cases={r["_id"]:r for r in iter_array(f) if r["_id"] in qids}
        assert set(cases)==qids
        keys={r["answer_id"] for r in cases.values()}
        with z.open(goldsrc["members"]["id_aliases.json"]) as f:aliases={r["Q_id"]:r for line in f if (r:=json.loads(line))["Q_id"] in keys}
    names=read(PARENT/"chosen-titles.json.gz");pred=read(PARENT/"predictions.json.gz")
    pool=read(PARENT/"novelty.json")["ever_unseen_ids"]
    armidx=read(PARENT/"prediction-seal.json")["arms"]
    metrics=("f1","em","full","recall");records={}
    for scenario,row in ctx.items():
        q=row["q"];g=cases[q];a=aliases.get(g["answer_id"],{})
        refs={g["answer"],*a.get("aliases",[]),*a.get("demonyms",[])}
        supporting={canon(t) for t,_ in g["supporting_facts"]}
        assert 0<len(supporting) and len({v[2] for v in row["refs"].values()})==1
        rec={}
        for arm,(j,key,n) in row["refs"].items():
            out=dict(f1=0.,em=0.,prec=0.,recall=0.);author.update_answer(out,ans[key]["answer"],refs)
            found=len(supporting&{canon(names[str(row["first"])][1]),canon(names[str(j)][1])})
            rec[arm]=[out["f1"],out["em"],int(found==len(supporting)),found/len(supporting)]
        records[scenario]=rec
    results={};rng=np.random.default_rng(523844)
    for mode,arms in [("fallback",("learned_href","learned_literal")),("census",("learned_dev","coord_cautious"))]:
        order=sorted(k for k in ctx if k.startswith(mode+"|"))
        scored=[ctx[k]["q"] for k in order]
        all_q=scored if mode=="fallback" else pool
        if mode=="census":
            assert len(all_q)==2374 and len(order)==10
            for q in set(all_q)-set(scored):
                assert pred[q]["choices"][armidx.index(arms[0])]==pred[q]["choices"][armidx.index(arms[1])]
        by_q={ctx[k]["q"]:np.array(records[k][arms[0]])-records[k][arms[1]] for k in order}
        arr=np.array([by_q.get(q,np.zeros(4)) for q in all_q])
        seeds,index=np.unique([pred[q]["seed"] for q in all_q],return_inverse=True);den=np.bincount(index)
        aggregate=np.stack([np.bincount(index,weights=arr[:,j]) for j in range(4)],axis=1)
        draws=[]
        for _ in range(100):
            raw=rng.integers(len(den),size=(100,len(den)))
            draws.append(100*aggregate[raw].sum(axis=1)/den[raw].sum(axis=1)[:,None])
        ci=np.quantile(np.vstack(draws),[.025,.975],axis=0)
        paired={m:dict(delta_pp=100*arr[:,j].mean(),ci95_pp=list(ci[:,j]),wins=int((arr[:,j]>1e-12).sum()),losses=int((arr[:,j]< -1e-12).sum())) for j,m in enumerate(metrics)}
        gp=RUN/(mode+"-official-cases.json");ap=RUN/(mode+"-official-aliases.jsonl")
        dump=lambda p,x:p.write_text(json.dumps(x,ensure_ascii=True),encoding="ascii")
        dump(gp,[{k:cases[q][k] for k in ("_id","answer","answer_id")} for q in scored])
        ap.write_text("".join(json.dumps(x,ensure_ascii=True)+"\n" for x in aliases.values()),encoding="ascii")
        pol={};official={}
        for arm in arms:
            full=np.array([records[k][arm] for k in order])
            pol[arm]=dict(zip(metrics,(100*full.mean(0)).tolist()),full_count=int(full[:,2].sum()))
            predpath=RUN/(mode+arm+".json")
            dump(predpath,dict(answer={ctx[k]["q"]:ans[ctx[k]["refs"][arm][1]]["answer"] for k in order},sp={},evidence={}))
            buf=StringIO()
            with redirect_stdout(buf):author.eval(str(predpath),str(gp),str(ap))
            txt=buf.getvalue();off=json.loads(txt[txt.rfind("{"):]);official[arm]={m:off[m] for m in ("f1","em")}
            assert all(abs(off[m]-pol[arm][m])<.005001 for m in ("f1","em"))
        results[mode]=dict(n=len(all_q),generated_or_reused_rows=len(order),identical_imputed_delta_only=len(all_q)-len(order),
            clusters=len(seeds),paired=paired,signflip=sign_test(aggregate[:,0]),scored_subset_policies=pol,scored_subset_official=official,
            changed_addresses=sum(ctx[k]["refs"][arms[0]][0]!=ctx[k]["refs"][arms[1]][0] for k in order))
    put("results.json",results);put("records.json.gz",records)
    put("grade-seal.json",dict(results=hashfile(D/"results.json"),records=hashfile(D/"records.json.gz"),answers=hashfile(D/"answer-seal.json"),
        official=goldsrc["evaluator"],gold=goldsrc["archive"],code=hashfile(Path(__file__))))
    print(json.dumps(results,ensure_ascii=False))
if __name__=="__main__":grade()
