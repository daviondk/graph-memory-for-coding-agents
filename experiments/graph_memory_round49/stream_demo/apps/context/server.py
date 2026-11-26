"""Interactive exact packet reconstruction on three real, de-identified edits."""
import argparse,json,sqlite3
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from mechanism import match, project
D=Path(__file__).resolve().parent
MODES=("file","range","edges","local")
SCENARIOS=("edges","interior","changed")
def database(name):
    return sqlite3.connect((D/name).as_uri()+"?mode=ro&immutable=1",uri=True)

def choose(rows,budget):
    head=[];used=0
    for i,c,g in rows:
        if used+c>budget//2:break
        head.append(i);used+=c
    states={0:(0,0)}
    for i,c,g in rows[len(head):]:
        for cost,(v,mask) in list(states.items()):
            newcost=cost+c
            if newcost+used>budget:continue
            proposal=(v+g,mask | (1<<i))
            old=states.get(newcost)
            if old is None or (proposal[0],-proposal[1])>(old[0],-old[1]):
                states[newcost]=proposal
    _,mask=max(states.values(),key=lambda item:(item[0],-item[1]))
    return head+[i for i,c,g in rows[len(head):] if mask&(1<<i)]

def query(name,policy,budget,inspect):
    if name not in SCENARIOS or policy not in MODES or budget not in (512,1024,2048):
        raise ValueError("Unknown selection")
    db=database("reader.sqlite")
    try:
        begin,end,delta,nbytes=db.execute("select begin,end,delta,argument_bytes from edit where id=?",(name,)).fetchone()
        rows=db.execute("select unit,affected,lo,hi,cost,gain from node where id=? order by unit",(name,)).fetchall()
        parts=[list(x[0] for x in db.execute("select tag from literal where id=? and version=? order by n",(name,v))) for v in (0,1)]
    finally:db.close()
    edge,inner,_=match(*parts)
    live={};info=[]
    for i,hit,lo,hi,c,g in rows:
        addr=[lo,hi] if not hit else None
        if hit and policy!="file":
            addr=project(lo,hi,begin,end,delta,{"range":{},"edges":edge,"local":inner}[policy])
        if addr:live[i]=addr
        info.append(dict(id=i,old=[lo,hi],new=addr,bytes=c,on_path=bool(hit)))
    pool=[(i,c,g) for i,_,_,_,c,g in rows]
    old=choose(pool,budget);selected=choose([r for r in pool if r[0] in live],budget)
    out=dict(prior=old,selected=selected,reused=old==selected,blocks=info,begin=begin,end=end,delta=delta,
        bytes=nbytes,old_tags=[t[:6] for t in parts[0]],new_tags=[t[:6] for t in parts[1]],
        edges=len(edge),interior=len(inner)-len(edge))
    if inspect:
        conn=database("audit.sqlite");checked=0;bad=0
        try:
            snap={(v,n):tag for v,n,tag in conn.execute("select version,n,tag from snapshot where id=?",(name,))}
            for i,n,seen in conn.execute("select unit,n,tag from seen where id=?",(name,)):
                if i not in selected:continue
                dest=n+live[i][0]-next(b["old"][0] for b in info if b["id"]==i)
                bad+=int(snap[0,n]!=seen or snap[1,dest]!=seen);checked+=1
        finally:conn.close()
        out["audit"]=dict(lines=checked,mismatches=bad)
    return out

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=urlsplit(self.path)
        if path.path=="/":
            data=(D/"index.html").read_bytes();kind="text/html; charset=utf-8";status=200
        elif path.path in ("/packet","/audit"):
            q=parse_qs(path.query)
            try:
                obj=query(q["case"][0],q["policy"][0],int(q["budget"][0]),path.path=="/audit");status=200
            except (KeyError,IndexError,ValueError):
                obj={"error":"Unknown selection"};status=400
            data=json.dumps(obj).encode();kind="application/json"
        else:self.send_error(404);return
        self.send_response(status);self.send_header("Content-Type",kind);self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
    def log_message(self,*args):pass
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--port",type=int,default=8779);s=ThreadingHTTPServer(("127.0.0.1",p.parse_args().port),Handler)
    print(f"http://127.0.0.1:{s.server_port}",flush=True)
    try:s.serve_forever()
    except KeyboardInterrupt:pass
    finally:s.server_close()
