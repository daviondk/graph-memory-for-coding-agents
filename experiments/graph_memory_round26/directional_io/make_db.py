from collections import defaultdict,Counter
from functools import lru_cache
from time import perf_counter_ns
import os,sqlite3,sys
from cfg import *
sys.path.insert(0,str(R))
from dataset import c,ro,CACHE,squad_rows
def main():
    freeze();P.mkdir(exist_ok=True,parents=True)
    if DB.exists():
        z=load(D/"build.json");assert z["db"]==sha_file(DB) and z["cases"]==sha_file(D/"cases.json.gz");print("reused",z["n"]);return
    temp=P/"building.sqlite"
    if temp.exists():raise FileExistsError(temp)
    pools={};requests={}
    for name in ("ise","mdd","squad"):
        p=R/f"{name}-opened.json.gz";assert sha_file(p)==load(R/f"{name}-open-seal.json")["actions"]
        baseline=load(R/f"{name}-choices.json.gz");opens=load(p)
        eligible=[q for q,x in opens.items() if len(x["arms"]["both"])==2 and all(op[1]<op[2] for op in x["arms"]["both"])]
        ids=sorted(eligible,key=lambda q:sha(("direction-io-v1/"+q).encode()))[:96];assert len(ids)==96
        by={}
        if name=="mdd":
            by={i:z[2] for i,z in enumerate(c.get_views()["documents"])}
        if name=="squad":by={t:txt for t,txt,_ in squad_rows()}
        reg=ro(R.parents[1]/"graph_memory_round23/read_causes/registry.sqlite") if name=="ise" else None
        for q in ids:
            r=baseline[q];e=r["cut"]["e"];t=r["t"];field=(name,t,e) if name!="mdd" else (name,"",e)
            if field not in pools:
                if name=="ise":
                    eid=reg.execute("select eid from address where t=? and e=?",(t,e)).fetchone()[0]
                    source=load(CACHE/f"{r['shard']}-{t}.json.gz")["fields"][eid]
                else:source=by[t if name=="squad" else e]
                pools[field]=source
            x=opens[q]["arms"];requests[name,q]=(field,x["both"],x["right"][0])
        if reg:reg.close()
    con=sqlite3.connect(temp);con.execute("pragma page_size=4096");con.execute("pragma journal_mode=delete");con.execute("pragma synchronous=FULL")
    tic=perf_counter_ns()
    con.execute("create table field(rid integer primary key,body text not null)")
    ordered=sorted(pools);rids={key:i+1 for i,key in enumerate(ordered)}
    con.executemany("insert into field values(?,?)",[(rids[key],pools[key]) for key in ordered]);con.commit()
    body_ns=perf_counter_ns()-tic
    tic=perf_counter_ns();con.execute("create table checkpoint(rid integer not null,c integer not null,b integer not null,primary key(rid,c)) without rowid")
    sparse={}
    for key,txt in pools.items():
        boundaries=[0];b=0
        while len(boundaries)*256<=len(txt):
            begin=(len(boundaries)-1)*256;b+=len(txt[begin:begin+256].encode());boundaries.append(b)
        sparse[key]=boundaries
    con.executemany("insert into checkpoint values(?,?,?)",[(rids[key],i*256,b) for key,v in sparse.items() for i,b in enumerate(v)])
    con.commit();index_ns=perf_counter_ns()-tic
    assert con.execute("pragma integrity_check").fetchone()[0]=="ok"
    pages={t:(n,pay) for t,n,pay in con.execute("select name,sum(pgsize),sum(payload) from dbstat group by name")}
    plans={k:con.execute("explain query plan "+sql,params).fetchall() for k,sql,params in (("one","select substr(body,?,?) from field where rid=?",(1,2,1)),("pair","select substr(body,?,?),substr(body,?,?) from field where rid=?",(1,2,4,2,1)),("checkpoint","select b from checkpoint where rid=? and c=?",(1,0)))}
    con.close();os.replace(temp,DB);out=[]
    for (name,q),(field,left_right,right) in sorted(requests.items()):
        txt=pools[field];points=sparse[field]
        def rec(op):
            e,l,h,n,anchor,side,nh=op
            def b(x):return points[x//256]+len(txt[x//256*256:x].encode())
            body=txt[l:h].encode();pre=f"[{e}:{anchor}] ".encode()
            return {"l":l,"h":h,"b":b(l),"z":b(h),"bytes":len(body),"sha":sha(body),"tokens":n,"header":pre.decode(),"side":side}
        both=[rec(op) for op in left_right];a=rec(right)
        wire=b"\n".join(x["header"].encode()+txt[x["l"]:x["h"]].encode() for x in both)
        out.append({"n":name,"q":q,"rid":rids[field],"field_bytes":len(txt.encode()),"field_chars":len(txt),"both":both,"right":a,"wire":sha(wire)})
    fees=save(D/"cases.json.gz",out)
    build={"plan":sha_file(D/"plan.json"),"db":sha_file(DB),"cases":fees,"database_bytes":DB.stat().st_size,"pages_table_bytes_and_payload":pages,
        "n":len(out),"unique_fields":len(pools),"unique_fields_by":dict(Counter(k[0] for k in pools)),"non_ascii_fields":sum(not s.isascii() for s in pools.values()),
        "nul_fields":sum("\x00" in s for s in pools.values()),"source_bytes":sum(len(s.encode()) for s in pools.values()),"checkpoint_rows":sum(map(len,sparse.values())),
        "body_insert_ns":body_ns,"checkpoint_build_insert_ns":index_ns,"query_plans":plans}
    receipt=D/"build.json"
    if receipt.exists():
        initial=load(receipt)
        for k in ("plan","db","cases","database_bytes","n","unique_fields","source_bytes","checkpoint_rows"):assert build[k]==initial[k],k
    else:save(receipt,build)
    print(build)
if __name__=="__main__":main()
