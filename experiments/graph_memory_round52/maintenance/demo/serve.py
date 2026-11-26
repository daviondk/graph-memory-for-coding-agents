"""Offline SQLite console. Run python serve.py and open the printed loopback address."""
import argparse
import html
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from engine import BASE_SCHEMA,advance,connect,setup,statement

ROOT=Path(__file__).resolve().parent
CASES=json.loads((ROOT/"cases.json").read_text(encoding="utf-8"))
LABELS={"change":"A mention changes the next document","below":"A mention remains below the leader","reinforce":"A mention strengthens the current leader"}

def replay(case,plan,received,asof,included):
    db=connect(":memory:")
    try:
        db.executescript(BASE_SCHEMA)
        db.execute("INSERT INTO cursor(q) VALUES(1)")
        db.executemany("INSERT INTO c VALUES(1,?,?,?,?,NULL)",[(c["id"],c["rank"],c["base"],c["boosted"]) for c in case["candidates"]])
        setup(db,plan)
        for step in range(1,received+1):
            ids=[c["id"] for c in case["candidates"] if c["seen"]==step and (included or c["id"]!=case["target"])]
            advance(db,1,step,ids)
        sql=statement(plan,received==asof)
        winner=db.execute(sql,(1,asof)).fetchone()[0]
        explain=[r[-1] for r in db.execute("EXPLAIN QUERY PLAN "+sql,(1,asof))]
        result=dict(winner=winner,explain=explain)
        if plan=="journal":
            rows=db.execute("SELECT step,id,score FROM history ORDER BY step").fetchall()
            edges=db.execute("SELECT count(*) FROM c WHERE seen IS NOT NULL").fetchone()[0]
            result.update(rows=rows,bound=1+edges,edges=edges)
        return result
    finally:db.close()

def evaluate(params):
    key=params.get("case","change")
    if key not in CASES:raise ValueError("Unknown case.")
    data=CASES[key]
    received=min(int(params.get("received",data["cuts"])),data["cuts"])
    asof=min(int(params.get("asof",received)),received)
    include=params.get("mention","1")
    if include not in ("0","1") or not 0<=asof<=received<=data["cuts"]:raise ValueError("Prefix or mention setting outside its range.")
    include=include=="1"
    journal=replay(data,"journal",received,asof,include)
    eligible=replay(data,"eligible",received,asof,include)
    other=replay(data,"journal",received,asof,not include)
    assert journal["winner"]==eligible["winner"]
    titles={c["id"]:c["title"] for c in data["candidates"]}
    ranking=[]
    for c in data["candidates"]:
        active=c["seen"] is not None and c["seen"]<=asof and (include or c["id"]!=data["target"])
        ranking.append(dict(title=c["title"],rank=c["rank"],id=c["id"],active=active,base=c["base"],
                            score=c["boosted"] if active else c["base"]))
    ranking.sort(key=lambda c:(-c["score"],c["rank"],c["id"]))
    assert ranking[0]["id"]==journal["winner"]
    return dict(case=key,first=data["first"],last=data["cuts"],received=received,asof=asof,mention=int(include),
        target=titles[data["target"]],mention_span=data["witness"],mention_step=next(c["seen"] for c in data["candidates"] if c["id"]==data["target"]),
        observed_words=min(received*16,data["tokens"]),asof_words=min(asof*16,data["tokens"]),journal=journal,eligible=eligible,
        journal_title=titles[journal["winner"]],eligible_title=titles[eligible["winner"]],toggled_title=titles[other["winner"]],
        changed=other["winner"]!=journal["winner"],ranking=ranking,history=[dict(step=t,title=titles[j],score=s) for t,j,s in journal["rows"]])

def escape(value):return html.escape(str(value),quote=True)

def render(data):
    opts="".join(f'<option value="{k}" {"selected" if data["case"]==k else ""}>{v}</option>' for k,v in LABELS.items())
    select=lambda name,limit,actual: '<select name="'+name+'">'+''.join(f'<option {"selected" if j==actual else ""}>{j}</option>' for j in range(limit+1))+'</select>'
    versions=select("received",data["last"],data["received"])
    asofs=select("asof",data["last"],data["asof"])
    present=data["mention"]
    flag=f'<select name="mention"><option value="1" {"selected" if present else ""}>Include observed mention</option><option value="0" {"selected" if not present else ""}>Omit mention in replay</option></select>'
    rows="".join(f'<tr><td>{escape(c["title"])}</td><td>{c["rank"]}</td><td>{c["base"]:.5f}</td><td>{str(c["active"]).lower()}</td><td>{c["score"]:.5f}</td></tr>' for c in data["ranking"])
    history="".join(f'<li>Version {h["step"]} &nbsp; {escape(h["title"])} &nbsp; <code>{h["score"]:.5f}</code></li>' for h in data["history"])
    contrast="Changes" if data["changed"] else "Preserves"
    jt=escape(data["journal_title"]);et=escape(data["eligible_title"])
    scenarios=' &nbsp; '.join(f'<a href="/?case={k}">{escape(v)}</a>' for k,v in LABELS.items())
    plans=''.join('<p><strong>'+k+'</strong><br><code>'+escape(" / ".join(data[k]["explain"]))+'</code></p>' for k in ("eligible","journal"))
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Versioned retrieval in SQLite</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:960px;margin:3rem auto;padding:0 1rem;color:#1a2936;background:#fafbf9}}h1,h2{{line-height:1.15}}h2{{margin-top:2rem}}form,section{{background:white;border:1px solid #cad2d1;padding:1rem;border-radius:5px}}label{{display:inline-block;margin:0 .8rem .5rem 0}}select,button{{display:block;font:inherit;padding:.22rem}}a{{color:#005a66}}table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid #dfe5e4;text-align:left;padding:.35rem}}code{{overflow-wrap:anywhere}}button{{background:#154e4b;color:white;border:0;padding:.4rem 1rem}}</style>
<h1>Versioned retrieval in SQLite</h1>
<p>Choose a replay for a real first passage. Each reveal verifies the next 16 normalized words. The journal stores each improvement in the top-ranked document's score or tie priority.</p>
<nav>{scenarios}</nav><h2>{escape(data["first"])}</h2>
<form><label>Scenario<select name="case">{opts}</select></label><label>Received through version{versions}</label><label>Read as of version{asofs}</label><label>Counterfactual{flag}</label><button>Replay in SQLite</button></form>
<p>Received {data["observed_words"]} words. Reading version {data["asof"]}, covering {data["asof_words"]} words. Future read requests are clamped to the received prefix.</p>
<p>The exact mention <strong>{escape(data["target"])}</strong> occupies normalized words {data["mention_span"][0]}–{data["mention_span"][1]} and becomes visible at version {data["mention_step"]}. Omitting it suppresses that edge during replay of the same trace.</p>
<section><b>Journal winner</b> &nbsp;{jt}<br><b>Fresh eligible-index lookup</b> &nbsp;{et}<br><b>Toggling this mention</b> &nbsp;{contrast.lower()} the retrieved address. Opposite setting returns {escape(data["toggled_title"])}.</section>
<h2>Score at the requested version</h2><table><tr><th>Candidate document</th><th>Tie rank</th><th>Base score</th><th>Confirmed mention</th><th>Score</th></tr>{rows}</table>
<h2>Persistent journal at the received version</h2><p>{len(data["history"])} stored version(s), bounded by one initial entry + {data["journal"]["edges"]} verified edge(s) = {data["journal"]["bound"]} entries.</p><ol>{history}</ol>
<details><summary>SQLite query plans</summary>{plans}</details>
<footer><p>Scenarios use frozen full-passage scores. The experiment measures exact historical document selection for monotone edge updates. It does not measure generated answer quality or online recomputation of the base score.</p></footer></html>"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self,format,*args):
        pass

    def do_GET(self):
        url=urlsplit(self.path)
        if url.path not in ("/","/api"):
            self.send_error(404);return
        try:
            data=evaluate({k:v[0] for k,v in parse_qs(url.query).items()})
        except (ValueError,OverflowError):
            self.send_error(400,"Invalid replay controls");return
        api=url.path=="/api"
        body=(json.dumps(data,ensure_ascii=False) if api else render(data)).encode("utf-8")
        self.send_response(200);self.send_header("Content-Type",("application/json" if api else "text/html")+"; charset=utf-8")
        self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=8052)
    args=parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1",args.port),Handler) as server:
        print(f"http://127.0.0.1:{server.server_port}/",flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
