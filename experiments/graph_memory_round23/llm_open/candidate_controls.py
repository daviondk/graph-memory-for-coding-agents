"""Supplementary strategies sealed prior to individual label access."""
from prepare import *
def predict():
    inputs=read(D/"menus.json.gz");tok=Tokenizer.from_file(str(TOK))
    assert sha(D/"menus.json.gz")==read(D/"plan-lock.json")["menus"]
    chosen={}
    for row in inputs:
        src=read(CACHE/f"{row['shard']}-{row['t']}.json.gz")
        question=trim(tok,dict(src["q"])[row["q"]],160)
        db=sqlite3.connect((SOURCE/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
        fields={e:src["fields"][eid] for e,eid in db.execute("SELECT e,eid FROM address WHERE t=?",(row["t"],))}
        db.close();pol={}
        for fmt,a in row["arms"].items():
            windows=[(e,start,fields[e][start:end]) for e,start,end in a["displayed"]]
            assert len(windows)==len(a["candidates"])
            assert [[e,l] for e,l,_ in windows]==a["candidates"]
            rr=lexical_order(windows,question);assert rr[0]==a["bm25"]
            pol[fmt]=next(i for i in rr if windows[i][0]==windows[0][0])
        chosen[row["q"]]=pol
    write(D/"extra-choices.json",chosen)
    write(D/"extra-lock.json",dict(choices=sha(D/"extra-choices.json"),menus=sha(D/"menus.json.gz"),
          protocol=sha(D/"EXTRA_CONTROLS_RU.md"),code=sha(Path(__file__))))
def score():
    from evaluate_open import m
    choices=read(D/"extra-choices.json");el=read(D/"extra-lock.json")
    assert sha(D/"extra-choices.json")==el["choices"]
    assert sha(D/"sql-reads.json.gz")==read(D/"open-seal.json")["reads"]
    gold=read(D.parents[1]/"graph_memory_round18/isetrace_official/gold-spans.json.gz");out=[]
    db=sqlite3.connect((SOURCE/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    for row in read(D/"sql-reads.json.gz"):
        q,t=row["q"],row["t"];truth=[]
        for s in gold[q]:
            match=db.execute("SELECT e FROM address WHERE t=? AND eid=? AND ptr=?",(t,s["event_id"],s["json_pointer"])).fetchone()
            truth.append([match[0] if match else -1,s["char_start"],s["char_end"]])
        arms={}
        for fmt,b in row["arms"].items():
            vals=[m.measure(truth,[rec["span"]])[0] for rec in b["options"]]
            g=vals[choices[q][fmt]]
            arms[fmt]={"within_first_field":[g[0],g[2]],"uniform_expected":[sum(v[0] for v in vals)/len(vals),sum(v[2] for v in vals)/len(vals)]}
        out.append({"q":q,"fmt":arms})
    db.close();write(D/"extra-scores.json.gz",out)
    n=len(out);tbl={f:{k:[sum(z["fmt"][f][k][j] for z in out)/n for j in (0,1)] for k in ("within_first_field","uniform_expected")} for f in ("short","merged")}
    write(D/"extra-results.json",dict(columns=["full_support","coverage"],n=n,summary=tbl,scores=sha(D/"extra-scores.json.gz"),
          choices=sha(D/"extra-lock.json"),open=sha(D/"open-seal.json")));print(tbl)
if __name__=="__main__":
    globals()[sys.argv[1]]()
