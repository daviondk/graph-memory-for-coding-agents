"""Independent confirmation audit from immutable visible ranks, prompts and original labels."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

D=Path(__file__).resolve().parent
BASE=D.parent
sys.path.insert(0,str(BASE))
from study import raw,digest
from sql_check import DB_SCHEMA
from verify_complete import check_matching


def main():
    root=BASE.parent/"routing"
    fixed=raw(D/"fixed.json")
    assert all(digest(BASE.parent/p)==h for p,h in fixed.items())
    seal=raw(D/"predictions-seal.json")
    for k,p in (("choices",D/"choices.json.gz"),("script",D/"driver.py"),("fixed",D/"fixed.json"),
                ("flags",root/"flags.json.gz"),("orders",root/"orders.json.gz"),("lex",root/"lex-orders.json.gz")):
        assert digest(p)==seal[k]
    choices=raw(D/"choices.json.gz"); ranks=raw(root/"orders.json.gz")
    lex=raw(root/"lex-orders.json.gz");flags=raw(root/"flags.json.gz");model=raw(BASE/"model.json")
    assert len(choices)==1280 and not set(choices)&set(raw(BASE/"hotpot-decisions.json.gz"))
    db=sqlite3.connect(":memory:");db.execute(DB_SCHEMA)
    for q,r in ranks.items():
        dense,linked=r["dense"],r["linked_dense"];l=lex[q]
        assert choices[q]["dense"]==dense and choices[q]["linked"]==linked
        gap=r["scores"][str(dense)]-r["scores"][str(linked)]
        assert choices[q]["gate"]==(linked if gap<=0.04178261756896973 else dense)
        assert choices[q]["router"]==(dense if flags[q] else linked)
        features={}
        for j,i in enumerate(r["order"]):
            s=str(i)
            row=[q,i,j,r["scores"][s],l["question_rank"][s],l["snippet_rank"][s],int(i in r["edges"])]
            db.execute("INSERT INTO candidates VALUES(?,?,?,?,?,?,?)",row)
            features[i]=[row[3],1/(row[4]+1),1/(row[5]+1),1/(j+1),row[6]]
        for name in ("graph","hybrid"):
            w=model[name]["coef"];v=lambda i:sum((x-m)/s*c for x,m,s,c in zip(features[i],model["mean"],model["scale"],w))
            assert choices[q][name+"_pair"]==max((dense,linked),key=v)
        gain=model["answer_gain"]["intercept"]+sum((x-y)/s*c for x,y,s,c in zip(features[linked],features[dense],model["scale"],model["answer_gain"]["coef"]))
        assert choices[q]["answer_pair"]==(linked if gain>0 else dense)
    for name in ("hybrid","graph"):
        w=model[name]["coef"];sql=(BASE/"rank.sql").read_text(encoding="utf8")
        co={f"w{i}":(w[i]/s if i<len(w) else 0.) for i,s in enumerate(model["scale"])}
        assert dict(db.execute(sql,co))=={q:v[name] for q,v in choices.items()}
    db.close()
    ctx=raw(D/"contexts.json.gz");rp=raw(D/"replay.json");new=raw(D/"new-answers.json.gz");np=raw(D/"new-prompts.json.gz")
    old_ctx=raw(root/"contexts.json.gz");oldp=raw(root/"prompts.json.gz");olda=raw(root/"answers.json.gz")
    old_clusters={z["cluster"] for z in raw(BASE.parent/"transfer"/"contexts.json.gz").values()}
    assert not ({z["cluster"] for z in old_ctx.values()}&old_clusters)
    assert all(current==olda[k] for k,current in rp.items()) and len(rp)==12
    assert len(new)==len(np)==raw(D/"answer-seal.json")["n_new"] and set(new)==set(np)
    assert all(digest(D/f)==raw(D/"grade-seal.json")[k] for k,f in
               (("records","records.json.gz"),("results","results.json"),("answers","answer-seal.json")))
    records=raw(D/"records.json.gz");result=raw(D/"results.json");gold=raw(root/"gold.json.gz")
    check_matching("hotpot",root,choices,old_ctx,oldp,olda,new,np,ctx,gold,records,result,["full","recall","f1","em"],True)
    print("Verified 1,280 prospective decisions for nine policies, both full rankings in SQLite, "
          f"{len(new)} new exact prompts, 12 GPU controls, official-equivalent metrics, intervals and sign-flip.")

if __name__=="__main__":
    main()
