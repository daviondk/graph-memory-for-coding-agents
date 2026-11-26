"""Local, read-only address chooser over the exact 2Wiki evaluation snapshot."""
import argparse,json,math,sqlite3
from contextlib import closing
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

ROOT=Path(__file__).resolve().parent
FILTERS={"all":"1","gain":"label='gain'","loss":"label='loss'","switched":"label!='unchanged'","unchanged":"label='unchanged'"}
def database():
    con=sqlite3.connect((ROOT/"address.sqlite").as_uri()+"?mode=ro&immutable=1",uri=True)
    con.row_factory=sqlite3.Row
    return con
def one(db,sql,args=()):
    row=db.execute(sql,args).fetchone()
    if row is None:raise KeyError("Episode not found")
    return dict(row)
def threshold(value,frozen):
    if value=="always":return "always",None
    if value=="registered":return "registered",frozen
    t=float(value)
    if not math.isfinite(t) or not 0<=t<=2:raise ValueError("threshold must be between 0 and 2")
    return "custom",t

def read_answer(db,episode,ordinal,snapshot,required=None):
    query="""SELECT a.ordinal,a.snapshot,a.prompt_sha,a.input_tokens,r.output AS answer,a.f1
        FROM archived a JOIN response r ON a.snapshot=r.snapshot AND a.prompt_sha=r.prompt_sha
        WHERE a.episode=? AND a.ordinal=? AND a.snapshot=?"""
    args=[episode,ordinal,snapshot]
    if required is not None:
        query+=" AND a.prompt_sha=?";args.append(required)
    row=db.execute(query,args).fetchone()
    return dict(row) if row is not None else None

def detail(db,key,setting,snapshot=None,requested_prompt=None):
    ep=one(db,"SELECT id,question,first_title,first_id,snippet FROM episode WHERE id=?",(key,))
    metadata=dict(db.execute("SELECT key,value FROM metadata").fetchall())
    frozen=float(metadata["threshold"]);mode,t=threshold(setting,frozen)
    rows=[dict(r) for r in db.execute("SELECT ordinal,rank,title,cosine,mentioned FROM candidate WHERE episode=? ORDER BY rank",(key,))]
    dense=rows[0];linked=next((r for r in rows if r["mentioned"]),dense)
    gap=dense["cosine"]-linked["cosine"]
    chosen=linked if mode=="always" or gap<=t else dense
    live=metadata["snapshot"] if snapshot is None else snapshot
    base=read_answer(db,key,dense["ordinal"],live)
    active=read_answer(db,key,chosen["ordinal"],live,requested_prompt)
    return dict(episode=ep,candidates=rows,registered=frozen,mode=mode,threshold=t,gap=gap,dense=dense["ordinal"],
        mentioned=linked["ordinal"] if linked["mentioned"] else None,selected=chosen["ordinal"],changed=chosen!=dense,
        snapshot=metadata["snapshot"],model_sha=metadata["model"],baseline_answer=base,selected_answer=active)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,code,content,kind):
        data=content if isinstance(content,bytes) else json.dumps(content,ensure_ascii=False,allow_nan=False).encode()
        self.send_response(code);self.send_header("Content-Type",kind+"; charset=utf-8");self.send_header("Content-Length",str(len(data)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(data)
    def do_GET(self):
        path=urlsplit(self.path);args=parse_qs(path.query,keep_blank_values=True)
        def arg(name,default=None):return args.get(name,[default])[0]
        if path.path=="/":
            self.send(200,(ROOT/"index.html").read_bytes(),"text/html");return
        try:
            with closing(database()) as db:
                if path.path=="/api/health":
                    m=dict(db.execute("SELECT key,value FROM metadata").fetchall())
                    result=dict(ok=True,count=int(m["count"]),threshold=float(m["threshold"]),snapshot=m["snapshot"])
                elif path.path=="/api/cases":
                    f=arg("filter","all")
                    if f not in FILTERS:raise ValueError("Unknown filter")
                    limit=int(arg("limit","24"));offset=int(arg("offset","0"))
                    if not 1<=limit<=1280 or offset<0:raise ValueError("Invalid offset or limit")
                    where=FILTERS[f]
                    total=db.execute("SELECT count(*) FROM episode WHERE "+where).fetchone()[0]
                    rows=[dict(r) for r in db.execute("SELECT id,question FROM episode WHERE "+where+" ORDER BY id LIMIT ? OFFSET ?",(limit,offset))]
                    result=dict(filter=f,total=total,items=rows)
                elif path.path=="/api/case":
                    result=detail(db,arg("id"),arg("threshold","registered"),arg("snapshot"),arg("prompt"))
                elif path.path=="/api/gold":
                    r=one(db,"SELECT aliases,supports FROM gold WHERE episode=?",(arg("id"),))
                    result={k:json.loads(v) for k,v in r.items()}
                else:raise KeyError("Route not found")
            self.send(200,result,"application/json")
        except KeyError as e:self.send(404,{"error":e.args[0]},"application/json")
        except (ValueError,OverflowError) as e:self.send(400,{"error":str(e)},"application/json")
if __name__=="__main__":
    cli=argparse.ArgumentParser();cli.add_argument("--port",type=int,default=0);args=cli.parse_args()
    with ThreadingHTTPServer(("127.0.0.1",args.port),Handler) as server:
        print(f"http://127.0.0.1:{server.server_port}/",flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass

