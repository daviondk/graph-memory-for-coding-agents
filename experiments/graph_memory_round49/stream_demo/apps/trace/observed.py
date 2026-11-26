"""Recorded FEEDS updates and independent optimization of the visible evidence packet."""
from contextlib import closing
import json
from urllib.parse import urlsplit,parse_qs
from weights import BASE, connect
SCALE=1<<32

def calculate(nodes, changes, cap, subset):
    prices=[];utilities=[]
    shifts={i:b for i,a,b in changes if i in subset}
    for rank,(i,c,links) in enumerate(nodes,1):
        prices.append(c)
        counts=sum(min(cap,shifts.get(source,previous)) for source,previous in links)
        utilities.append((SCALE+rank//2)//rank+counts*(SCALE//16))
    used=0;prefix=0
    for c in prices:
        if used+c>1024:break
        used+=c;prefix+=1
    capacity=2048-used
    score=[0]*(capacity+1);decisions=[]
    for cost,utility in zip(prices[prefix:],utilities[prefix:]):
        take=bytearray(capacity+1)
        for w in range(capacity,cost-1,-1):
            v=score[w-cost]+utility
            if v>score[w]:
                score[w]=v;take[w]=1
        decisions.append(take)
    tail=[]
    for j in reversed(range(prefix,len(nodes))):
        if decisions[j-prefix][capacity]:
            capacity-=prices[j];tail.append(nodes[j][0])
    return [n[0] for n in nodes[:prefix]]+tail[::-1]

def handle_observed(handler):
    url=urlsplit(handler.path)
    if url.path=="/observed":
        handler.send(200,"text/html; charset=utf-8",(BASE/"observed.html").read_bytes())
        return True
    if not url.path.startswith("/api/observed/"):return False
    try:
        with closing(connect(BASE/"runtime/observed.sqlite")) as db:
            if url.path=="/api/observed/catalog":
                pairs=db.execute("SELECT q,step FROM event ORDER BY q,step").fetchall()
                handler.data(dict(groups=pairs,example=["q25",9]));return True
            if url.path not in ("/api/observed/show","/api/observed/check"):
                handler.data({"error":"Unknown resource"},404);return True
            p=parse_qs(url.query,keep_blank_values=True);q=p["q"][0];step=int(p["step"][0]);cap=int(p["cap"][0])
            row=db.execute("SELECT nodes,updates FROM event WHERE q=? AND step=?",(q,step)).fetchone()
            if row is None or cap not in (1,4):raise ValueError("Unknown group or policy")
            nodes,updates=map(json.loads,row);ids={a for a,_,_ in updates}
            raw=p.get("set",["all"])[0]
            selected=sorted(ids) if raw=="all" else sorted(set(int(a) for a in raw.split(",") if a))
            if not set(selected)<=ids:raise ValueError("Producer outside this transaction")
            def get(subset):
                key=",".join(map(str,subset))
                r=db.execute("SELECT ids FROM chosen WHERE q=? AND step=? AND cap=? AND subset=?",(q,step,cap,key)).fetchone()
                if r is None:raise ValueError("Choose one source, a pair or the entire transaction")
                return json.loads(r[0])
            base=get([]);after=get(selected);cost={i:c for i,c,_ in nodes}
            singles=[dict(id=a,before=v,after=w,preserves=get([a])==base) for a,v,w in updates]
            data=dict(q=q,step=step,cap=cap,selected=selected,updates=singles,base=base,after=after,
                      old_tokens=sum(cost[i] for i in base),new_tokens=sum(cost[i] for i in after),count=len(nodes))
            if url.path.endswith("/check"):
                independent=calculate(nodes,updates,cap,selected)
                data["checked"]=independent==after;data["members"]=independent
            handler.data(data)
    except (ValueError,KeyError) as exc:handler.data(dict(error=str(exc)),400)
    return True
