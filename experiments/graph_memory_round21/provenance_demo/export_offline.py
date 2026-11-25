"""Export a self-contained reviewer copy from the checked SQLite history."""
import hashlib
import json
from pathlib import Path
from store import DATA,connect

D=DATA.parent
db=connect();data=[]
for t,n in db.execute("SELECT t,steps FROM trace ORDER BY t"):
    events=list(db.execute("SELECT kind,call FROM event WHERE t=? ORDER BY step",(t,)))
    kinds={"message":0,"tool_call":1,"tool_output":2}
    packed_events=[[kinds[k],c] for k,c in events]
    endpoints=list(db.execute("SELECT call,called,returned FROM endpoint WHERE t=? ORDER BY call",(t,)))
    assert [r[0] for r in endpoints]==list(range(1,len(endpoints)+1)) and n==len(events)
    windows=list(db.execute("SELECT a,b,lo,hi,count FROM witness WHERE t=? ORDER BY a,b,lo",(t,)))
    why=list(db.execute("SELECT a,b,step,value_id,cause,other FROM reason WHERE t=? ORDER BY a,b,step,value_id",(t,)))
    stops=list(db.execute("SELECT step,final,gold FROM checkpoint WHERE t=? ORDER BY step",(t,)))
    data.append({"t":t,"e":packed_events,"p":[v[1:] for v in endpoints],"w":windows,"c":stops,"why":why})
db.close()
source=(D/"index.html").read_text(encoding="utf8")
anchor="async function fetchJSON(path){"
assert source.count(anchor)==1
packed=json.dumps(data,separators=(",",":"),ensure_ascii=True).replace("<","\\u003c")
js="""const histories=CASES_PLACEHOLDER;
async function fetchJSON(path){
const [route, query]=path.split("?");const p=new URLSearchParams(query);
if(route==='/api/cases')return histories.map(c=>({t:c.t,steps:c.e.length}));
const c=histories.find(c=>c.t===p.get('t'));if(!c)throw Error('Unknown history');
if(route==='/api/edge'){const a=+p.get('a'),b=+p.get('b'),step=+p.get('step');
 const windows=c.w.filter(x=>x[0]===a&&x[1]===b&&x[2]<=step).map(([, ,start,end,count])=>({start,end:end!==null&&end<=step?end:null,count}));
 const evidence=c.why.filter(x=>x[0]===a&&x[1]===b&&x[2]<=step).map(([, ,step,value,cause,other])=>({step,value,cause,other}));
 return {windows,evidence}}
if(route!=='/api/view')throw Error('Unknown route');const step=+p.get('step'), m=new Map();
for(const [a,b,lo,hi,n] of c.w){const current=lo<=step&&(hi===null||step<hi);
 const append=lo<=step;const final=hi===null&&c.p[a-1][1]<=step&&c.p[b-1][0]<=step;
 if(!current&&!append&&!final)continue;
 const key=a+'-'+b;const v=m.get(key)||{a,b,witnesses:0,exact:false,append:false,final:false};
 if(current){v.exact=true;v.witnesses=n} v.append||=append;v.final||=final;m.set(key,v)}
const kind=['message','tool_call','tool_output'][c.e[step][0]];
return {t:c.t,step,steps:c.e.length,kind,call:c.e[step][1],edges:[...m.values()],
 checkpoints:c.c.map(([step,final,gold])=>({step,final:!!final,gold}))}}
async function unusedNetworkReader(path){""".replace("CASES_PLACEHOLDER",packed)
source=source.replace(anchor,js)
start=source.index("async function unusedNetworkReader(")
end=source.index("const params=",start)
source=source[:start]+source[end:]
source=source.replace("SQLite provenance explorer","Offline replay · SQLite snapshot")
(D/"explorer.html").write_text(source,encoding="utf8")
print(len(data),(D/"explorer.html").stat().st_size)

