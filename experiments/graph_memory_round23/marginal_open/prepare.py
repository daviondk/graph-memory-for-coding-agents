"""Construct fixed field lengths and strict visible-only selector packages, without gold."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from time import perf_counter
import sqlite3
from common import D,W,PARENT,PRIVATE,TOK,read,sha,save,check_plan
CACHE=__import__("pathlib").Path("D:/CodexResearch/x20-isetrace-e5-gpu/cache/projection")
def shard(i):
    f=PARENT/f"receipts-{i}.json.gz";assert sha(f)==read(PARENT/"receipt-lock.json")["files"][f.name]
    inp=read(PARENT/"inputs.json");assert sha(PARENT/"registry.sqlite")==inp["registry_sha"]
    reg=sqlite3.connect((PARENT/"registry.sqlite").as_uri()+"?mode=ro&immutable=1",uri=True)
    gr=defaultdict(list)
    for r in read(f):gr[r["t"]].append(r)
    vals=[];sizes=[];chars=0
    for t,records in sorted(gr.items()):
        raw=read(CACHE/f"{i}-{t}.json.gz");body=raw["fields"];qtext=dict(raw["q"])
        addr=dict(reg.execute("select e,eid from address where t=?",(t,)));assert set(addr.values())==set(body) or set(addr.values())<=set(body)
        sizes.extend((t,e,len(body[eid])) for e,eid in addr.items())
        for r in records:
            q=r["q"];tok,cbyte,parts,digest=r["arms"]["ratio/merged"]["paid"]["2048"]
            vis=[(e,l,body[addr[e]][l:h]) for e,l,h in parts]
            assert all(len(text)==h-l for (e,l,text),(ef,lf,h) in zip(vis,parts,strict=True))
            vals.append({"t":t,"q":q,"question":qtext[q],"fragments":vis,"paid":tok,"wire":digest})
            chars+=sum(len(z[2]) for z in vis)
    reg.close();vf=PRIVATE/f"visible-{i}.json.gz";sf=PRIVATE/f"sizes-{i}.json.gz"
    save(vf,vals);save(sf,sizes)
    return {"visible":sha(vf),"sizes":sha(sf),"n":len(vals),"t":len(gr),"chars":chars}
def main():
    check_plan();PRIVATE.mkdir(parents=True,exist_ok=True);start=perf_counter()
    with ProcessPoolExecutor(2) as ex:rows=list(ex.map(shard,range(8)))
    path=D/"field-lengths.sqlite";temp=PRIVATE/"lengths.build.sqlite"
    if not path.exists():
        if temp.exists():raise FileExistsError("Preserving incomplete build: "+str(temp))
        c=sqlite3.connect(temp)
        c.execute("create table field_size(t text,e integer,n integer not null,primary key(t,e)) without rowid")
        for i in range(8):
            s=PRIVATE/f"sizes-{i}.json.gz";assert sha(s)==rows[i]["sizes"]
            c.executemany("insert into field_size values(?,?,?)",read(s))
        c.commit();c.execute("vacuum");c.close();temp.replace(path)
    c=sqlite3.connect(path.as_uri()+"?mode=ro&immutable=1",uri=True)
    assert c.execute("pragma integrity_check").fetchone()==("ok",)
    totals=c.execute("select count(*),count(distinct t),sum(n) from field_size").fetchone();c.close()
    assert totals[:2]==(72184,1207) and sum(v["n"] for v in rows)==2000
    save(D/"visible-seal.json",{"parts":rows,"catalog":sha(path),"catalog_bytes":path.stat().st_size,"fields":totals[0],"trajectories":totals[1],"source_chars":totals[2],"seconds_build_including_private_projection":perf_counter()-start,"original_registry":sha(PARENT/"registry.sqlite"),"tokenizer":sha(TOK),"plan":sha(D/"plan.json"),"code":sha(__import__("pathlib").Path(__file__))})
if __name__=="__main__":main()

