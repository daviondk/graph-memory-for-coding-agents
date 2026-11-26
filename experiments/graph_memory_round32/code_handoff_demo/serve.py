"""Inspect immutable observations without loading source text or executing traces."""
import argparse,json,sqlite3
from contextlib import closing
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs

ROOT=Path(__file__).resolve().parent
def connect():
    db=sqlite3.connect((ROOT/"handoff.sqlite").as_uri()+"?mode=ro&immutable=1",uri=True)
    db.row_factory=sqlite3.Row
    return db

def cases(db):
    return [dict(r) for r in db.execute("select g,issue,target_path,cp,routed from cases order by issue,cp,g")]

def detail(db,g):
    record=db.execute("select * from cases where g=?",(g,)).fetchone()
    if record is None:raise ValueError("Unknown handoff")
    r=dict(record);r["targets"]=json.loads(r.pop("target_json"))
    r["addresses"]=[dict(t) for t in db.execute("""select o.*, exists(select 1 from catalog c where c.cp=o.cp and c.idx=o.idx) as sent
        from observations o where o.cp=? order by sent desc,path,idx desc""",(r["cp"],))]
    return r

def opened(db,g,idx,strategy,budget,start=None,end=None):
    case=detail(db,g)
    if strategy not in ("forward","boundary") or not 0<=budget<=512:raise ValueError("Invalid reading configuration")
    if start is not None and start<1 or end is not None and end<1 or start is not None and end is not None and end<start:raise ValueError("Invalid line interval")
    targets=case["targets"]
    rows=[];used=0
    if idx is not None:
        info=next((a for a in case["addresses"] if a["idx"]==idx),None)
        if info is None:raise ValueError("Unknown observation in this snapshot")
        available=[dict(r) for r in db.execute("select line_no,fp,wp from lines where cp=? and idx=? and (? is null or line_no>=?) and (? is null or line_no<=?) order by ord",(case["cp"],idx,start,start,end,end))]
        order=list(range(len(available)))
        if strategy=="boundary":
            order.sort(key=lambda i:(min(i,len(available)-1-i),i))
        for i in order:
            line=available[i]
            if used+line["wp"]<=budget:rows.append(line);used+=line["wp"]
        signs={(line["line_no"],line["fp"]) for line in rows} if info["path"]==case["target_path"] else set()
    else:
        info=None;signs=set()
    hits=[tuple(k) in signs for k in targets]
    return {"observation":info,"rows":rows,"read_wp":used,"address_wp":case["address_wp"],"hits":hits,
            "target_lines":targets,"boundary_pair":all(hits[:2]),"interior_pair":all(hits[2:]),
            "published_route":idx==case["routed"],"target_path":case["target_path"]}

def response(url):
    u=urlsplit(url);v={k:a[0] for k,a in parse_qs(u.query).items()}
    if u.path=="/":return 200,"text/html",(ROOT/"index.html").read_bytes()
    def number(key):
        val=v.get(key)
        return int(val) if val is not None else None
    with closing(connect()) as db:
        if u.path=="/api/cases":data=cases(db)
        elif u.path=="/api/presets":data=json.loads((ROOT/"verified.json").read_bytes())["presets"]
        elif u.path=="/api/case":data=detail(db,v.get("q",""))
        elif u.path=="/api/open":data=opened(db,v.get("q",""),number("idx"),v.get("read","forward"),int(v.get("budget",512)),number("start"),number("end"))
        else:return 404,"text/plain",b"Not found"
    return 200,"application/json",json.dumps(data).encode()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:status,kind,body=response(self.path)
        except ValueError as e:status,kind,body=400,"application/json",json.dumps({"error":str(e)}).encode()
        self.send_response(status);self.send_header("Content-Type",kind+"; charset=utf-8");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--port",type=int,default=8087)
    with ThreadingHTTPServer(("127.0.0.1",p.parse_args().port),Handler) as server:
        print(f"http://127.0.0.1:{server.server_port}/",flush=True);server.serve_forever()
