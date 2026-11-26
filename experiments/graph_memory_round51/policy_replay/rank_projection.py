"""Project the graded, equal-token-budget ranker trial into an inspectable SQLite database."""
import argparse
from pathlib import Path
import sqlite3
import replay

BASE=replay.ROOT.parent/"baseline"
OFFLINE={"adaptive_address":"r50-adaptive-address","gate_confirmation":"r50-gate-confirmation","hotpot":"r51-hotpot-gate","confirm":"r51-hotpot-routing"}

def project(dest, scratch):
    if dest.exists():
        raise FileExistsError("Choose a fresh destination")
    data=replay.read(BASE/"complete-records.json.gz")
    contexts=replay.read(BASE/"matched-contexts.json.gz")
    weights=replay.read(BASE/"model.json")
    new=replay.read(BASE/"new-answers.json.gz")
    decisions=replay.read(BASE/"decisions.json.gz")
    decisions["hotpot"]=replay.read(BASE/"hotpot-decisions.json.gz")
    confirmed=BASE/"confirm"
    contexts["confirm"]=replay.read(confirmed/"contexts.json.gz")
    data["confirm"]=replay.read(confirmed/"records.json.gz")
    decisions["confirm"]=replay.read(confirmed/"choices.json.gz")
    new.update(replay.read(confirmed/"new-answers.json.gz"))
    with sqlite3.connect(dest) as db:
        db.executescript("""
        CREATE TABLE question(panel TEXT,q TEXT,question TEXT,fragment TEXT,first_title TEXT,label TEXT,PRIMARY KEY(panel,q)) WITHOUT ROWID;
        CREATE INDEX by_effect ON question(panel,label,q);
        CREATE TABLE candidate(panel TEXT,q TEXT,cid INTEGER,title TEXT,cos REAL,qr INT,sr INT,dr INT,edge INT,PRIMARY KEY(panel,q,cid)) WITHOUT ROWID;
        CREATE TABLE response(panel TEXT,q TEXT,cid INT,prompt TEXT,input_tokens INT,answer TEXT,f1 REAL,full INT,PRIMARY KEY(panel,q,cid)) WITHOUT ROWID;
        CREATE TABLE coef(policy TEXT PRIMARY KEY,w0 REAL,w1 REAL,w2 REAL,w3 REAL,w4 REAL) WITHOUT ROWID;
        CREATE TABLE summary(panel TEXT,arm TEXT,f1 REAL,full REAL,PRIMARY KEY(panel,arm)) WITHOUT ROWID;
        """)
        for arm in ("graph","hybrid"):
            coefficients=list(weights[arm]["coef"])
            coefficients+= [0.]*(5-len(coefficients))
            db.execute("INSERT INTO coef VALUES(?,?,?,?,?,?)",(arm,*(w/s for w,s in zip(coefficients,weights["scale"]))))
        for panel, rows in contexts.items():
            corpus={"hotpot":replay.ROOT.parent/"transfer","confirm":replay.ROOT.parent/"routing"}.get(panel,replay.R50/panel)
            orders=replay.read(corpus/"orders.json.gz")
            lex=replay.read(corpus/"lex-orders.json.gz")
            receipts=replay.read(corpus/"catalog-receipts.json.gz")
            labels=replay.read(scratch/("x20-"+OFFLINE[panel])/"catalog-input.json.gz")
            source_titles={q:{i:t for i,t,body in v[1]} for q,v in replay.read(scratch/("x20-"+OFFLINE[panel])/"visible.json.gz").items()}
            answers=replay.read(corpus/"answers.json.gz")
            answers.update(new)
            for q,row in sorted(rows.items()):
                question,fragment,catalog=labels[q]
                check=receipts[q]
                assert replay.digest(question.encode())==check["question"] and replay.digest(fragment.encode())==check["snippet"]
                scores=data[panel][q]
                diff=scores["graph"]["f1"]-scores["hybrid"]["f1"]
                label="gain" if diff>0 else "loss" if diff<0 else "tie"
                db.execute("INSERT INTO question VALUES(?,?,?,?,?,?)",(panel,q,question,fragment,source_titles[q][check["first"]],label))
                title=dict(catalog)
                for j,i in enumerate(orders[q]["order"]):
                    k=str(i)
                    assert replay.digest(title[i].encode())==check["titles"][k]
                    db.execute("INSERT INTO candidate VALUES(?,?,?,?,?,?,?,?,?)",
                               (panel,q,i,title[i],orders[q]["scores"][k],lex[q]["question_rank"][k],lex[q]["snippet_rank"][k],j,int(i in orders[q]["edges"])))
                lookup={}
                budgets=set()
                for arm,(i,h,n) in row["refs"].items():
                    assert decisions[panel][q][arm]==i
                    value=(panel,q,i,h,n,answers[h]["answer"],scores[arm]["f1"],scores[arm]["full"])
                    assert lookup.setdefault(i,value)==value
                    budgets.add(n)
                assert len(budgets)==1
                db.executemany("INSERT INTO response VALUES(?,?,?,?,?,?,?,?)",lookup.values())
            for arm in ("dense","gate","linked","graph","hybrid"):
                values=[r[arm] for r in data[panel].values()]
                db.execute("INSERT INTO summary VALUES(?,?,?,?)",(panel,arm,100*sum(v["f1"] for v in values)/len(values),100*sum(v["full"] for v in values)/len(values)))
        db.commit()
        assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)

if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("dest",type=Path)
    ap.add_argument("--scratch",type=Path,default=Path("D:/CodexResearch"))
    args=ap.parse_args();project(args.dest,args.scratch)

