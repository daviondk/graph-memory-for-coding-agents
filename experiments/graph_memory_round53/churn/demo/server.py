"""SQLite time-travel demonstration on one signed archival trace. No network dependencies."""
import argparse
from contextlib import closing
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import sqlite3
import sys
from urllib.parse import parse_qs,urlsplit

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from engine import Engine,RAW,PREV,CURRENT
from source import encode,sha,sig

TRACE=json.loads((HERE/"trace.json").read_bytes())
EVENTS=TRACE["trace"];EPISODE=TRACE["episode"]
assert TRACE["trace_sha256"]==sha(encode(EVENTS)) and len(EVENTS)==TRACE["max_revision"]
assert all(e["sha"]==sig(e["born"],e["delta"]) for e in EVENTS)

def plan(c,sql,params):
    return [v[-1] for v in c.execute("EXPLAIN QUERY PLAN "+sql,params)]
def state(horizon,version):
    if not 0<=version<=horizon<=len(EVENTS):
        raise ValueError("Required: 0 <= version <= horizon <= "+str(len(EVENTS)))
    # The two independent connections contain the same event prefix, each with its actual physical plan.
    with closing(sqlite3.connect(":memory:",isolation_level=None)) as raw,closing(sqlite3.connect(":memory:",isolation_level=None)) as log:
        a=Engine(raw,"interval",create=True);b=Engine(log,"journal",create=True)
        for event in EVENTS[:horizon]:
            for eng in (a,b):
                eng.apply(EPISODE,event["t"],event["born"],event["delta"])
        def vs(t):
            calc=a.history(EPISODE,t);record=b.history(EPISODE,t)
            assert calc==record==a.get(EPISODE,t)==b.get(EPISODE,t)
            return {"interval":calc,"journal":record}
        observed=vs(version);current=vs(horizon);before=vs(horizon-1) if horizon else None
        event=EVENTS[horizon-1] if horizon else None
        selected_changes=[]
        for src,dst,d in event["delta"] if event else ():
            rows=raw.execute("SELECT beg,end,weight FROM edge WHERE q=? AND src=? AND dst=? AND beg<=? ORDER BY beg",
                             (EPISODE,src,dst,horizon)).fetchall()
            find=lambda t:next((w for begin,end,w in rows if begin<=t and (end is None or t<end)),0)
            prior,now=find(horizon-1),find(horizon);assert now-prior==d
            selected_changes.append({"from":src,"to":dst,"delta":d,"was":prior,"now":now})
        transitions=log.execute("SELECT rev,cid,score FROM winner WHERE q=? ORDER BY rev",(EPISODE,)).fetchall()
        witness=log.execute("SELECT rev,cid,score FROM winner WHERE q=? AND rev<=? ORDER BY rev DESC LIMIT 1",(EPISODE,version)).fetchone()
        counts={"available":raw.execute("SELECT COUNT(*) FROM source").fetchone()[0],
                "open_edges":raw.execute("SELECT COUNT(*) FROM edge WHERE end IS NULL").fetchone()[0],
                "edge_intervals":raw.execute("SELECT COUNT(*) FROM edge").fetchone()[0],"winner_entries":len(transitions)}
        return {"episode":EPISODE,"max_revision":len(EVENTS),"horizon":horizon,"version":version,
                "query":observed,"current":current,"previous_commit":before,"transitions":transitions,
                "predecessor_record":witness,"counts_at_horizon":counts,"changes_at_horizon":selected_changes,
                "born_at_horizon":event["born"] if event else [],
                "message_boundary":TRACE["boundaries"][horizon-1] if event else None,
                "plans":{"interval":plan(raw,RAW,(version,version,EPISODE,version)),
                         "journal":plan(log,PREV,(EPISODE,version)),
                         "current":plan(log,CURRENT,(EPISODE,))},
                "receipt_sha256":event["sha"] if event else None,"fixture_sha256":TRACE["fixture_sha256"],
                "trace_sha256":TRACE["trace_sha256"]}
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,code,data,kind):
        self.send_response(code);self.send_header("Content-Type",kind);self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(data)
    def do_GET(self):
        u=urlsplit(self.path)
        if u.path in ("/","/index.html"):
            self.send(200,(HERE/"index.html").read_bytes(),"text/html; charset=utf-8");return
        if u.path=="/api/health":
            self.send(200,b'{"status":"ok","episode":"q11"}',"application/json");return
        if u.path!="/api/state":
            self.send(404,b"Not found","text/plain");return
        try:
            values=parse_qs(u.query)
            horizon=int(values.get("horizon",["17"])[0])
            version=int(values.get("version",[str(min(16,horizon))])[0])
            body=state(horizon,version)
        except (ValueError,OverflowError) as e:
            self.send(400,json.dumps({"error":str(e)}).encode(),"application/json");return
        self.send(200,json.dumps(body,separators=(",",":")).encode(),"application/json")

def main():
    p=argparse.ArgumentParser();p.add_argument("--port",type=int,default=0);args=p.parse_args()
    with ThreadingHTTPServer(("127.0.0.1",args.port),Handler) as server:
        print("http://127.0.0.1:"+str(server.server_address[1]),flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass

if __name__=="__main__":main()

