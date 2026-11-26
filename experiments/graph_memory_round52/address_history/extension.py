"""Run the original console plus a comparison of score and address histories."""
from pathlib import Path
import sys
D=Path(__file__).resolve().parent
if not (D/"serve.py").is_file():
    sys.path.insert(0,str(D.parent/"maintenance"/"demo"))
import argparse
import json
import struct
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs,urlsplit
import serve
from address_store import plan_setup,read_pair
from engine import BASE_SCHEMA,advance,connect

def materialize(case,plan,row):
    db=connect(":memory:")
    try:
        db.executescript(BASE_SCHEMA);db.execute("INSERT INTO cursor(q) VALUES(1)")
        db.executemany("INSERT INTO c VALUES(1,?,?,?,?,NULL)",[(x["id"],x["rank"],x["base"],x["boosted"]) for x in case["candidates"]])
        plan_setup(db,plan)
        for step in range(1,row["received"]+1):
            ids=[x["id"] for x in case["candidates"] if x["seen"]==step and (row["mention"] or x["id"]!=case["target"])]
            advance(db,1,step,ids)
        idx,score=db.execute(read_pair(plan),(1,row["asof"])).fetchone()
        fields="step,id,score" if plan=="journal" else "step,id"
        changes=[list(r) for r in db.execute("SELECT "+fields+" FROM history WHERE q=1 ORDER BY step")]
        return dict(id=idx,score=score,bits=struct.pack(">d",score).hex(),rows=changes)
    finally:db.close()

def compare(params):
    row=serve.evaluate({"case":"reinforce",**params});case=serve.CASES[row["case"]]
    full=materialize(case,"journal",row);compact=materialize(case,"address",row)
    equal=full["id"]==compact["id"] and full["bits"]==compact["bits"]
    assert equal
    titles={x["id"]:x["title"] for x in case["candidates"]}
    for v in (full,compact):v["title"]=titles[v["id"]]
    return dict(case=row["case"],first=case["first"],last=case["cuts"],received=row["received"],asof=row["asof"],mention=row["mention"],
        witness=row["target"],witness_step=row["mention_step"],span=row["mention_span"],full=full,compact=compact,equal=equal,titles=titles)

def render(row):
    e=serve.escape;labels=serve.LABELS
    cases=''.join(f'<option value="{k}" {"selected" if k==row["case"] else ""}>{v}</option>' for k,v in labels.items())
    def options(name):
        return f'<select name="{name}">'+''.join(f'<option {"selected" if n==row[name] else ""}>{n}</option>' for n in range(row["last"]+1))+'</select>'
    toggle=''.join(f'<option value="{n}" {"selected" if n==row["mention"] else ""}>{v}</option>' for n,v in [(1,"Verify real mention"),(0,"Suppress in replay")])
    def table(name):
        is_full=name=="full"
        body="".join(f'<tr><td>{r[0]}</td><td>{r[1]}</td><td>{e(row["titles"][r[1]])}</td>'+ (f'<td>{r[2]:.8f}</td>' if is_full else '')+'</tr>' for r in row[name]["rows"])
        return '<table><thead><tr><th>Version</th><th>ID</th><th>Winner</th>'+('<th>Stored score</th>' if is_full else '')+'</tr></thead><tbody>'+body+'</tbody></table>'
    full,compact=row["full"],row["compact"]
    scenarios=' &nbsp; '.join(f'<a href="/compact?case={k}">{e(v)}</a>' for k,v in labels.items())
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Compact version history</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:940px;margin:3rem auto;padding:0 1rem;color:#1a2936;background:#fafbf9}}h1,h2{{line-height:1.2}}form,section{{background:white;border:1px solid #c7d1d0;border-radius:5px;padding:1rem}}label{{display:inline-block;margin:0 .7rem .6rem 0}}select,button{{display:block;font:inherit}}button{{background:#154e4b;color:white;border:0;padding:.45rem 1rem}}a{{color:#005a66}}table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;border-bottom:1px solid #dfe5e4;padding:.3rem}}code{{overflow-wrap:anywhere}}</style>
<nav><a href="/">Versioned retrieval console</a></nav>
<h1>Compact version history</h1><p>Store a version when the winner changes address. Its score at a historical prefix can be recovered from the original candidate and the time its edge was confirmed.</p>
<nav>{scenarios}</nav><h2>{e(row["first"])}</h2><form><label>Scenario<select name="case">{cases}</select></label><label>Received through{options("received")}</label><label>Read as of{options("asof")}</label><label>Evidence<select name="mention">{toggle}</select></label><button>Replay both SQLite plans</button></form>
<p>Witness <strong>{e(row["witness"])}</strong> occupies words {row["span"][0]}–{row["span"][1]}, receivable at version {row["witness_step"]}. Reading version {row["asof"]} of {row["received"]} received.</p>
<section><strong>Both plans return {e(full["title"])}</strong>, ID {full["id"]}. The full history returns {full["score"]:.8f}; the compact plan reconstructs {compact["score"]:.8f}. Both yield IEEE-754 bits <code>{full["bits"]}</code>.</section>
<h2>Full history · {len(full["rows"])} stored rows</h2>{table("full")}
<h2>Address history · {len(compact["rows"])} stored rows</h2>{table("compact")}
<p>Scores and ranking priorities are frozen before replay. Both plans receive identical ordered, monotone edge updates. Row counts only cover persistent history. Candidate scores and their edge receipts remain available to both plans.</p></html>"""

class Handler(serve.Handler):
    def do_GET(self):
        url=urlsplit(self.path)
        if url.path not in ("/","/compact","/api/compact"):
            return super().do_GET()
        args={k:v[0] for k,v in parse_qs(url.query).items()}
        try:
            if url.path=="/":
                body=serve.render(serve.evaluate(args)).replace("<h1>",'<nav><a href="/compact">Compact version history</a></nav><h1>',1)
            else:
                data=compare(args)
                body=json.dumps(data,ensure_ascii=False) if url.path=="/api/compact" else render(data)
        except (ValueError,OverflowError):
            self.send_error(400,"Invalid replay controls");return
        body=body.encode("utf-8")
        self.send_response(200);self.send_header("Content-Type",("application/json" if url.path=="/api/compact" else "text/html")+"; charset=utf-8")
        self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--port",type=int,default=8052);args=parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1",args.port),Handler) as server:
        print(f"http://127.0.0.1:{server.server_port}/",flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
