"""Interactive aggregation of measured SQL index work across actual Git commits."""
import argparse
from contextlib import closing
import gzip
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit

HERE=Path(__file__).resolve().parent
SCHEMA="""
CREATE TABLE observed (w INTEGER, repo TEXT, rev TEXT, policy TEXT, probes INTEGER, returned INTEGER);
CREATE INDEX obs_filter ON observed (w,policy,repo);
CREATE TABLE cold (w INTEGER,repo TEXT, policy TEXT, probes INTEGER, returned INTEGER);
"""
QUERY="""
SELECT policy,count(*) AS commits,sum(probes) AS probes,sum(returned) AS rows
FROM observed WHERE w=? AND policy IN (?,?) AND (?='all' OR repo=?)
GROUP BY policy ORDER BY policy
"""
COLD="""
SELECT policy,sum(probes),sum(returned) FROM cold
WHERE w=? AND policy IN (?,?) AND (?='all' OR repo=?) GROUP BY policy ORDER BY policy
"""


def build(db, path):
    with gzip.open(path, "rt", encoding="utf8") as f:
        log=json.load(f)
    db.executescript(SCHEMA)
    for window, projects in log["windows"].items():
        for repo, projection in projects.items():
            policies=projection["policies"]
            for rev,_,counters,*_ in projection["events"]:
                assert len(counters)==len(policies)
                db.executemany("INSERT INTO observed VALUES(?,?,?,?,?,?)",
                    [(int(window),repo,rev,name,cost[0],cost[1]) for name,cost in zip(policies,counters)])
            db.executemany("INSERT INTO cold VALUES(?,?,?,?,?)",
                [(int(window),repo,name,values[0],values[1]) for name,values in projection["cold"].items()])
    db.commit()
    db.execute("PRAGMA query_only=ON")


def get(db, query, vm):
    args=parse_qs(query,keep_blank_values=True,max_num_fields=4)
    if set(args)-{"w","repo","basis","cap"} or any(len(v)!=1 for v in args.values()):
        raise ValueError("Invalid control")
    params={k:v[0] for k,v in args.items()}
    w=int(params.get("w","32")); cap=int(params.get("cap","8"))
    repo=params.get("repo","all"); basis=params.get("basis","bytes")
    repos=[r[0] for r in db.execute("SELECT DISTINCT repo FROM cold ORDER BY repo")]
    if w not in (16,32,64) or cap not in (8,12) or basis not in ("slots","bytes") or repo not in ["all",*repos]:
        raise ValueError("Unknown control value")
    classic=cap+int(basis=="bytes")
    bound=cap
    values=(w,"classic"+str(classic),"partial"+str(bound),repo,repo)
    cold={method:[probes,rows] for method,probes,rows in db.execute(COLD,values)}
    plans=[]
    for method, count, probes, rows in db.execute(QUERY,values):
        n=classic if method.startswith("classic") else bound
        plans.append(dict(method=method,slots=n,payload=8*(n+int(method.startswith("partial"))),
                          commits=count,probes=probes,rows=rows,cold=cold[method]))
    if w == 32:
        measured = vm["total"] if repo=="all" else vm["projects"][repo]
        for plan in plans:
            sample=measured.get(plan["method"])
            if sample:
                assert sample["warm"]["executions"]==plan["probes"] and sample["warm"]["returned_rows"]==plan["rows"]
                plan["warm_vm_steps"]=sample["warm"]["vm_steps"]
    assert len(plans)==2 and plans[0]["commits"]==plans[1]["commits"]
    return dict(w=w,cap=cap,basis=basis,repo=repo,repos=repos,plans=plans,query=QUERY.strip())


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url=urlsplit(self.path)
        if url.path=="/":
            self.reply(200,"text/html; charset=utf-8",(HERE/"index.html").read_bytes())
        elif url.path=="/api/compare":
            try:
                value=get(self.server.db,url.query,self.server.vm)
                self.reply(200,"application/json; charset=utf-8",json.dumps(value).encode())
            except ValueError as e:
                self.reply(400,"text/plain",str(e).encode())
        else:
            self.send_error(404)

    def reply(self,code,mime,body):
        self.send_response(code);self.send_header("Content-Type",mime)
        self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)

    def log_message(self,*args):
        pass


if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument("--port",type=int,default=0)
    args=cli.parse_args()
    path=HERE/"events.json.gz"
    if not path.is_file():
        path=HERE.parents[1]/"cochange/events.json.gz"
    with closing(sqlite3.connect(":memory:")) as db, HTTPServer(("127.0.0.1",args.port),Handler) as http:
        build(db,path); http.db=db
        vm_file=HERE/"vm-steps.json"
        if not vm_file.is_file():
            vm_file=HERE.parents[1]/"cochange/physical/vm-steps.json"
        http.vm=json.loads(vm_file.read_bytes())
        print(f"http://127.0.0.1:{http.server_port}/",flush=True)
        http.serve_forever()
