"""Apply each prediction as an actual state overlay on an inert copy of public faulty traces."""
from collections import Counter
import sqlite3
from project import OUT,PRIV,PRE,get,save
def main():
    db=PRIV/"selective-state.sqlite";con=sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS node(task TEXT NOT NULL, id TEXT NOT NULL, kind TEXT NOT NULL, PRIMARY KEY(task,id)) WITHOUT ROWID;
    CREATE TABLE IF NOT EXISTS deactivated(task TEXT NOT NULL, method TEXT NOT NULL, id TEXT NOT NULL, PRIMARY KEY(task,method,id),
    FOREIGN KEY(task,id) REFERENCES node(task,id)) WITHOUT ROWID;
    PRAGMA foreign_keys=ON;
    """)
    count=Counter()
    for panel in ("controlled","adapted"):
        forecasts={r["id"]:r for r in get(OUT/(panel+"-forecasts.json.gz"))}
        for row in get(PRIV/(panel+"-blind.json.gz")):
            q=row["id"];f=forecasts[q];nodes=[(q,x["id"],"memory") for x in row["memory"]]+[(q,x["id"],x["type"]) for x in row["steps"]]
            with con:
                con.executemany("insert or ignore into node values(?,?,?)",nodes)
                assert set(con.execute("select task,id,kind from node where task=?",(q,)))==set(nodes)
                for name,x in f["arms"].items():
                    assert set(x["c"]).isdisjoint(x["m"])
                    con.executemany("insert or ignore into deactivated values(?,?,?)",[(q,name,u) for u in x["c"]+x["m"]])
                    state=con.execute("select n.id,n.kind from node n join deactivated d using(task,id) where n.task=? and d.method=?",(q,name)).fetchall()
                    assert set(x["c"])=={u for u,t in state if t=="claim"} and set(x["m"])=={u for u,t in state if t=="memory"} and len(state)==len(x["c"])+len(x["m"])
                    count[panel+"_method_cases"]+=1
    n=con.execute("select count(*) from node").fetchone()[0];f=con.execute("select count(*) from deactivated").fetchone()[0];assert con.execute("pragma foreign_key_check").fetchall()==[]
    con.close();save(OUT/"applied-receipt.json",dict(nodes=n,marks=f,methods_and_cases=count,scenario="separate reversible status overlays over faulty trace copy, without execution or replay"));print(count,n,f)
if __name__=="__main__":main()

