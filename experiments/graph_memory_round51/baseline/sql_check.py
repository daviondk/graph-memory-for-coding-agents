"""Check the SQLite ranking query against frozen Qwen+pairwise decisions."""
import sqlite3
from study import HERE,SOURCE,raw,save
DB_SCHEMA = """CREATE TABLE candidates (
   qid TEXT NOT NULL, candidate INTEGER NOT NULL, dense_rank INTEGER NOT NULL,
   cosine REAL NOT NULL, question_rank INTEGER NOT NULL, snippet_rank INTEGER NOT NULL,
   mention INTEGER NOT NULL CHECK (mention IN (0,1)), PRIMARY KEY (qid,candidate),
   UNIQUE (qid,dense_rank)
);"""

def main(write=False):
    m=raw(HERE/"model.json")
    pred=raw(HERE/"decisions.json.gz")
    pred["hotpot"]=raw(HERE/"hotpot-decisions.json.gz")
    db=sqlite3.connect(":memory:")
    sql=(HERE/"rank.sql").read_text(encoding="utf8")
    db.execute(DB_SCHEMA)
    info={}
    for panel,rows in pred.items():
        root=HERE.parent/"transfer" if panel=="hotpot" else SOURCE/panel
        rank=raw(root/"orders.json.gz");lex=raw(root/"lex-orders.json.gz")
        dat=[]
        for q,r in rank.items():
            l=lex[q]
            for j,i in enumerate(r["order"]):
                key=str(i)
                dat.append((q,i,j,r["scores"][key],l["question_rank"][key],l["snippet_rank"][key],int(i in r["edges"])))
        db.executemany("INSERT INTO candidates VALUES(?,?,?,?,?,?,?)",dat)
        for name in ("graph","hybrid"):
            coef=m[name]["coef"]
            w={f"w{i}":(coef[i]/s if i<len(coef) else 0.) for i,s in enumerate(m["scale"])}
            hits=dict(db.execute(sql,w))
            assert hits=={q:r[name] for q,r in rows.items()}
        info[panel]={"questions":len(rows),"candidate_rows":len(dat),"matched_selections":2*len(rows)}
        db.execute("DELETE FROM candidates")
    db.close()
    if write: save("sql-results.json",{"engine":sqlite3.sqlite_version,"panels":info})
    print("Verified two SQL policies across",sum(s["matched_selections"] for s in info.values()),"selections.")
    return info

if __name__=="__main__":
    main(True)
