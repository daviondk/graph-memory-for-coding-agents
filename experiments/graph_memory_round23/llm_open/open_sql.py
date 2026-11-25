"""Commit actual read-only SQL opens and candidate counterfactual reads before scoring."""
from prepare import *
from infer import atomic
def build_db(rows):
    path=PRIVATE/"field-payloads.sqlite"
    if path.exists():return path
    tmp=PRIVATE/"field-payloads-stage.sqlite"
    if tmp.exists():raise FileExistsError(tmp)
    db=sqlite3.connect(tmp)
    db.execute("CREATE TABLE field(t TEXT,e INTEGER,eid TEXT,ptr TEXT,body TEXT,PRIMARY KEY(t,e)) WITHOUT ROWID")
    reg=sqlite3.connect((SOURCE/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    with db:
        for r in rows:
            t=r["t"]; data=read(CACHE/f"{r['shard']}-{t}.json.gz")
            db.executemany("INSERT INTO field VALUES(?,?,?,?,?)",((t,e,eid,ptr,data["fields"][eid]) for e,eid,ptr in reg.execute("SELECT e,eid,ptr FROM address WHERE t=?",(t,))))
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    reg.close();db.close();os.replace(tmp,path)
    return path
def main():
    plan=read(D/"plan-lock.json");rl=read(D/"reader-lock.json")
    assert sha(D/"choices.json.gz")==rl["choices"] and sha(D/"menus.json.gz")==plan["menus"]
    rows=read(D/"menus.json.gz");choices=read(D/"choices.json.gz")
    dbpath=build_db(rows);sql=sqlite3.connect(dbpath.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    tok=Tokenizer.from_file(str(TOK));events=[];log=[]
    for r in rows:
        t,q=r["t"],r["q"];out={}
        def action(addr,key,kind):
            if addr is None:return {"span":[-1,0,0],"tokens":0,"text_sha":h("")}
            e,l=addr
            row=sql.execute("SELECT body FROM field WHERE t=? AND e=?",(t,e)).fetchone()
            assert row;body=row[0];e,l,stop,n=paid_open(tok,body,e,l)
            render=f"[{e}:{l}] "+body[l:stop]
            assert n==used(tok,render)<=256
            ret=dict(span=[e,l,stop],tokens=n,text_sha=h(render))
            log.append(dict(q=q,format=key,policy=kind,coordinate=[e,l],**ret))
            return ret
        for fmt,menu in r["arms"].items():
            ans=choices[menu["request"]]
            ix=AB.index(ans["letter"]) if ans["ok"] else None
            selections={k:menu[k] for k in ("first","bm25","bm25_before")};selections["qwen"]=ix
            got={k:action(menu["candidates"][i] if i is not None else None,fmt,k) for k,i in selections.items()}
            options=[action(addr,fmt,"opportunity") for addr in menu["candidates"]]
            assert all(v==options[i] for k,i in selections.items() if i is not None for v in [got[k]])
            out[fmt]=dict(chosen=selections,opened=got,options=options,ok=ans["ok"],usage=[ans.get("prompt_tokens",0),ans.get("completion_tokens",0)])
        events.append(dict(t=t,q=q,arms=out))
    sql.close();write(D/"sql-reads.json.gz",events);write(D/"sql-queries.json.gz",log)
    write(D/"open-seal.json",dict(reader=sha(D/"reader-lock.json"),menus=plan["menus"],sql=sha(dbpath),n_actual=sum(x["policy"]=="qwen" for x in log),
        n_all=len(log),reads=sha(D/"sql-reads.json.gz"),log=sha(D/"sql-queries.json.gz"),code=sha(Path(__file__))))
    print("sealed",sha(D/"open-seal.json"))
if __name__=="__main__":main()
