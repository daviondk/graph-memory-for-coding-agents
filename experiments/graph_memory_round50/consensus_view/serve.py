"""Inspect a budgeted vote over actual graph-reader outputs in an immutable SQLite snapshot."""
import argparse
import json
import sqlite3
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

D=Path(__file__).resolve().parent
SEEDS=(13,17,29,37,41)
METHODS=("votes_greedy","hamming_dp","mean_dp","votes_dp")

def connect():
    return sqlite3.connect((D/"consensus.sqlite").as_uri()+"?mode=ro&immutable=1",uri=True)

def query_pool(db,case,seeds):
    slots=",".join("?" for _ in seeds)
    # The planner has no reference to either evaluation table.
    rows=db.execute(f"""SELECT u.u,u.cost,u.role,r.seed,r.rank,r.utility,r.voted
        FROM unit u JOIN reader r ON r.q=u.q AND r.u=u.u
        WHERE u.q=? AND r.seed IN ({slots}) ORDER BY u.u,r.seed""",(case,*seeds))
    units={}
    for i,cost,role,seed,rank,utility,voted in rows:
        u=units.setdefault(i,dict(id=i,cost=cost,role=role,votes=0,total_utility=0.,reciprocal=0.,voters=[]))
        u["votes"]+=voted
        if voted:u["voters"].append(seed)
        u["total_utility"]+=utility
        u["reciprocal"]+=1/(60+rank)
    return sorted(units.values(),key=lambda u:(-u["reciprocal"],u["id"]))

def packet(rows,seeds,method,budget):
    room=budget
    head=0
    while head<len(rows) and budget-room+rows[head]["cost"]<=budget//2:
        room-=rows[head]["cost"];head+=1
    tail=[u for u in rows[head:] if u["cost"]<=room]
    picked=set()
    if method=="votes_greedy":
        for u in sorted(tail,key=lambda u:-u["votes"]):
            if u["cost"]<=room:
                picked.add(u["id"]);room-=u["cost"]
    else:
        cap=room
        best=[0.]*(cap+1)
        bits=[]
        for u in tail:
            val={"mean_dp":u["total_utility"]/len(seeds),"votes_dp":u["votes"],"hamming_dp":2*u["votes"]-len(seeds)}[method]
            cost=u["cost"]
            flags=bytearray(cap+1)
            for b in range(cap,cost-1,-1):
                trial=best[b-cost]+val
                if trial>best[b]:
                    best[b]=trial;flags[b]=1
            bits.append(flags)
        for u,b in reversed(list(zip(tail,bits))):
            if b[room]:picked.add(u["id"]);room-=u["cost"]
    return rows[:head]+[u for u in tail if u["id"] in picked],head

def inspect(db,case,seeds,method,budget,show_gold):
    if not 1<=case<=32 or not 128<=budget<=4096 or method not in METHODS or not seeds or not set(seeds)<=set(SEEDS) or len(seeds)!=len(set(seeds)):
        raise ValueError("Invalid reader configuration")
    rows=query_pool(db,case,seeds)
    retrieval,head=packet(rows,seeds,method,budget)
    ids=[u["id"] for u in retrieval]
    used=sum(u["cost"] for u in retrieval)
    assert used<=budget and len(ids)==len(set(ids))
    q,t=db.execute("SELECT benchmark_id,trajectory FROM question WHERE id=?",(case,)).fetchone()
    result=dict(question=q,trajectory=t,budget=budget,used=used,total=len(rows),method=method,
                head=head,readers=len(seeds),packet=ids,units=[dict(id=u["id"],role=u["role"],cost=u["cost"],
                votes=u["votes"],voters=u["voters"],selected=u["id"] in ids) for u in rows])
    if budget==2048 and set(seeds)==set(SEEDS):
        exemplar=db.execute("SELECT ids FROM reference WHERE q=? AND method=?",(case,method)).fetchone()
        result["archive_matches"]=json.loads(exemplar[0])==ids
    if show_gold:
        widths=dict(db.execute("SELECT atom,width FROM official_span WHERE q=?",(case,)))
        covered={a for a,i in db.execute("SELECT atom,u FROM official_member WHERE q=?",(case,)) if i in ids}
        total=sum(widths.values())
        result["evaluation"]=dict(covered=sum(widths[a] for a in covered),total=total,full=len(covered)==len(widths))
    return result

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url=urlsplit(self.path)
        if url.path=="/":
            blob=(D/"index.html").read_bytes();mime="text/html; charset=utf-8"
        elif url.path=="/packet":
            try:
                req=parse_qs(url.query)
                seeds=tuple(int(x) for x in req.get("seed",[str(s) for s in SEEDS]))
                with closing(connect()) as db:
                    data=inspect(db,int(req.get("case",["1"])[0]),seeds,req.get("method",[METHODS[0]])[0],
                                 int(req.get("budget",["2048"])[0]),req.get("gold")==["1"])
                blob=json.dumps(data).encode();mime="application/json"
            except (ValueError,IndexError):
                self.send_error(400);return
        else:
            self.send_error(404);return
        self.send_response(200);self.send_header("Content-Type",mime);self.send_header("Content-Length",str(len(blob)));self.end_headers();self.wfile.write(blob)
    def log_message(self,*args):pass

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=0)
    parser.add_argument("--no-browser",action="store_true")
    args=parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1",args.port),Handler) as server:
        url=f"http://127.0.0.1:{server.server_port}/"
        print(url,flush=True)
        if not args.no_browser:
            import webbrowser
            webbrowser.open(url)
        server.serve_forever()

