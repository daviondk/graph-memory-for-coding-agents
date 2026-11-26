"""Build a dependency-free HTML case replay from pinned public Git and registered SQLite receipts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

D = Path(__file__).resolve().parent
GIT = D.parent / "git_history"
sys.path.insert(0, str(GIT))
from generate import read, encode
from replay import method
from extension import extended
from partial import certify

REPO = "tox-dev/tox"
COMMIT = "62bd8cf9bfd5e8e5f3e8426b04645e6aa4ba5f0e"


def load():
    checks = read("verification.json")["hashes"] | read("stream-seal.json") | read("extension-seal.json")
    for path, digest in checks.items():
        assert hashlib.sha256((GIT/path).read_bytes()).hexdigest() == digest, path
    rows = read("streams.json.gz")[REPO]
    oracle = read("snapshot-oracle.json.gz")[REPO]
    paths = {cid:path for path,cid in read("path-ids.json.gz")[REPO].items()}
    costs,extra = read("event-costs.json.gz"),read("extension-costs.json.gz")
    pos = next(i for i,r in enumerate(rows) if r["sha"] == COMMIT)
    assert pos == 89
    blocks = rows[pos-1:pos+1]
    score = Counter()
    snapshots = []
    for i,row in enumerate(rows[:pos+1]):
        for cid in row["born"]:
            assert cid not in score
            score[cid] = 0
        for src,dst,delta in row["delta"]:
            score[src] += delta
        if i >= pos-1:
            ranked = sorted(score.items(), key=lambda v:(-v[1],v[0]))
            assert hashlib.sha256(encode(ranked)).hexdigest() == oracle[i]["all_scores_sha"]
            assert [list(p) for p in ranked[:8]] == oracle[i]["top8"]
            snapshots.append(dict(rev=row["sha"],t=row["t"],scores=dict(score),top=oracle[i]["top8"],policies={}))
    def create(db,plan,is_new):
        return method(db,plan,is_new) if plan=="classic12" else extended(db,plan,is_new)
    for l in (8,12):
        for kind in ("classic","partial"):
            plan=kind+str(l)
            archive=costs if plan=="classic12" else extra
            qcosts=archive["events"]["once"][plan][REPO]
            with sqlite3.connect(":memory:",isolation_level=None) as db:
                store=create(db,plan,True)
                cold_count=cold_rows=0
                for i,row in enumerate(rows[:pos+1]):
                    if i==1:
                        store=create(db,plan,False)
                    previous=store.last.get(REPO)
                    assert store.update(REPO,row)
                    receipt=dict(zip(archive["columns"],qcosts[i]))
                    for field in ("warm_probes","warm_rows","cold_probes","cold_rows","pairs"):
                        assert receipt[field]==store.event[field],(plan,row["t"],field)
                    if i:  # Start after base-build; operational restart on the first transition.
                        cold_count+=receipt["cold_probes"]
                        cold_rows+=receipt["cold_rows"]
                    if i<pos-1:
                        continue
                    snap=snapshots[i-pos+1]
                    query=dict(warm=receipt["warm_probes"],rows=receipt["warm_rows"],cold=receipt["cold_probes"],
                               coldRows=receipt["cold_rows"],earlierCold=cold_count-receipt["cold_probes"],
                               earlierColdRows=cold_rows-receipt["cold_rows"],pairs=receipt["pairs"])
                    old,prior_upper=previous[1]
                    query.update(oldEighth=list(old[7]),priorTail=list(old[-1]))
                    if kind=="partial":
                        ds={x:snap["scores"][x] for x in set(row["born"])|{a for a,b,d in row["delta"]}}
                        keep,upper,prefix=certify(previous[1],ds,l)
                        assert upper is not None and len(prefix)>=8 and store.event["warm_probes"]==0
                        assert keep[:8]==tuple(tuple(p) for p in snap["top"])
                        query.update(upper=list(upper),priorUpper=list(prior_upper),certified=len(prefix))
                    snap["policies"][plan]=query
    before=snapshots[0].pop("scores")
    after=snapshots[1].pop("scores")
    ids=sorted(after)
    assert ids==list(range(1,1+len(ids)))
    data=dict(repo=REPO,commits=snapshots,files=[paths[i] for i in ids],
              baseline=[before.get(i) for i in ids],born=blocks[1]["born"],edges=blocks[1]["delta"])
    for j,snap in enumerate(snapshots):
        for l in (8,12):
            a,b=(snap["policies"][p+str(l)] for p in ("classic","partial"))
            assert a["earlierCold"]==b["earlierCold"]==1 and a["earlierColdRows"]==b["earlierColdRows"]==l
            assert a["cold"]==b["cold"]==0
            assert a["warm"]==(1 if j==1 and l==8 else 0) and b["warm"]==0
    return data


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    data=json.dumps(load(),ensure_ascii=True,separators=(",",":")).replace("<","\\u003c")
    page=TEMPLATE.replace("%%DATA%%",data).replace("\r\n","\n").encode("utf-8")
    target=D/"index.html"
    if args.verify:
        assert target.read_bytes()==page
    else:
        target.write_bytes(page)
    print(len(page),"bytes",hashlib.sha256(page).hexdigest())


TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Why tox keeps its eighth file · Git replay</title>
<style>
*{box-sizing:border-box}html{background:#f3f2ec;color:#183231;font:16px/1.45 "Inter","Segoe UI",Arial,sans-serif}body{margin:0}main{width:min(1060px,100%);margin:0 auto;padding:34px 28px 26px}h1,h2,p{margin:0}h1{font-family:"Georgia",serif;font-weight:500;font-size:clamp(2rem,4.5vw,3.1rem);letter-spacing:-.046em;line-height:1.08}h2{font-size:1rem}.intro{color:#48615c;margin:9px 0 0;max-width:75ch}.head{border-bottom:1px solid #c0cdc3;padding-bottom:21px}.controls{margin:18px 0;display:flex;gap:15px 28px;flex-wrap:wrap}fieldset{border:0;margin:0;padding:0}legend{color:#3e574f;font-size:.79rem;font-weight:650;padding:0 0 5px}.seg{display:inline-flex;padding:3px;border:1px solid #bccbc0;border-radius:7px;background:#fff}button{appearance:none;border:0;background:transparent;color:#25413b;border-radius:4px;font:inherit;font-size:.87rem;cursor:pointer;padding:5px 11px}button[aria-pressed=true]{background:#214c41;color:white}button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #a76303;outline-offset:2px}
.grid{display:grid;grid-template-columns:1.05fr 1fr;gap:16px;align-items:start}.card{background:#fffef9;border:1px solid #c6d0c6;border-radius:10px;padding:17px 19px}.card h2{margin-bottom:10px}.proof{margin-bottom:14px}.scoreline{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid #d9e2d9;border-bottom:1px solid #d9e2d9;padding:11px 0;gap:6px}.scoreline label{display:block;font-size:.75rem;color:#4f635b}.scoreline strong{display:block;font-size:1.9rem;font-weight:600;line-height:1.05;color:#204a40;margin-bottom:4px}.caption,.explain,.small{font-size:.84rem;color:#455e55}.explain{margin-top:8px}.explain code,.small code{overflow-wrap:anywhere}.rank,.cost{border-collapse:collapse;width:100%;font-size:.86rem}.rank th,.cost th{font-size:.73rem;font-weight:600;color:#52665c}.rank th,.rank td,.cost th,.cost td{text-align:left;padding:4px 4px}.rank td:nth-child(n+3),.rank th:nth-child(n+3),.cost td:nth-child(n+2),.cost th:nth-child(n+2){text-align:right}.rank th{border-bottom:1px solid #cbd4cd}.rank tr+tr{border-top:1px solid #e4e9e2}.rank tr:last-child{background:#e3efe6;font-weight:650}.rank td:first-child{color:#53665c}.path{overflow-wrap:anywhere;line-height:1.25;font-family:"Consolas","Courier New",monospace;font-size:.79rem}.cost{margin:7px 0 12px}.cost tr{border-bottom:1px solid #dce4da}.cold{border-left:3px solid #b28843;background:#faf6e9;padding:7px 10px;font-size:.81rem;color:#374b41}.caption{margin-bottom:6px}.reference{margin-top:10px;font-size:.81rem;color:#506259}a{color:#165643;text-underline-offset:2px}details{padding-top:13px;font-size:.82rem;color:#445b51}summary{cursor:pointer;color:#294738}ul{margin:6px 0;padding-left:18px}.proof .subtitle{font-size:.8rem;color:#53645a}.status{margin-top:9px;color:#1c5940;font-size:.79rem}.hash{font-family:Consolas,monospace}footer{margin:16px 0 0;color:#516258;font-size:.76rem}
@media(max-width:720px){main{padding:20px 13px}.grid{grid-template-columns:1fr}.controls{gap:10px 16px}.card{padding:14px}.scoreline strong{font-size:1.65rem}}
</style></head><body><main>
<header class="head"><h1>Why tox keeps its eighth file</h1><p class="intro">A Git commit removes one net importer from <code>src/tox/config/cli/parser.py</code>. Can its eighth place still be certified from memory?</p></header>
<div class="controls">
<fieldset><legend>Git snapshot</legend><div class="seg"><button id="before" type="button" aria-pressed="false">Parent · 6c728a9c</button><button id="after" type="button" aria-pressed="true">Commit · 62bd8cf9</button></div></fieldset>
<fieldset><legend>Cache capacity L</legend><div class="seg"><button id="l8" type="button" aria-pressed="true">8 files</button><button id="l12" type="button" aria-pressed="false">12 files</button></div></fieldset>
</div><div class="grid">
<section class="card"><h2>Exact top 8</h2><p class="caption">Score counts distinct Python files importing this file.</p>
<table class="rank"><thead><tr><th scope="col">Rank</th><th scope="col">File</th><th scope="col">Score</th><th scope="col">Δ¹</th></tr></thead><tbody id="ranking"></tbody></table>
<p class="status" id="valid" role="status"></p>
<p class="reference">¹ Change from the parent shown here. Equal scores use the smaller persistent file ID first.</p>
<details><summary>What changed for this file?</summary><ul id="edgeList"></ul><p>The three changes are observed import edges between these two snapshots.</p></details>
</section>
<div><section class="card proof"><h2>Can the eighth file stay?</h2>
<div class="scoreline" aria-live="polite">
<div><strong id="priorScore"></strong><label>Eighth before update</label></div>
<div><strong id="eighthScore"></strong><label>Eighth after update</label></div>
<div><strong id="boundScore"></strong><label>Upper bound outside cache</label></div></div>
<p class="explain" id="reason"></p></section>
<section class="card"><h2>Measured index reads</h2><p class="caption">Ordered SQLite reads after applying this commit.</p>
<table class="cost"><thead><tr><th scope="col">Policy</th><th scope="col">Queries</th><th scope="col">Rows returned</th></tr></thead><tbody>
<tr><td>Variable exact prefix (Yi et al.)</td><td id="classicWarm"></td><td id="classicRows"></td></tr>
<tr><td>Stored upper bound + suffix</td><td id="partialWarm"></td><td id="partialRows"></td></tr></tbody></table>
<p class="cold">Previously paid per policy on this tox run: <strong id="coldProbes"></strong> cold query, <strong id="coldRows"></strong> rows. This commit adds <span id="localCold"></span> cold queries.</p></section></div></div>
<footer>Offline replay. Your browser ranks all tracked IDs using frozen per-file scores and signed import changes. Query counts come from the verified SQLite run on the continuous history; opening this page issues no SQL. <a id="source" target="_blank" rel="noreferrer">View selected Git commit</a> · <a href="https://cse.hkust.edu.hk/~yike/topk/icde03.pdf" target="_blank" rel="noreferrer">Yi et al., ICDE 2003</a>.</footer>
</main><script id="data" type="application/json">%%DATA%%</script>
<script>
"use strict";
const data=JSON.parse(document.getElementById("data").textContent);
const byId=id=>document.getElementById(id);
let snapshot=1, capacity=8;
function put(id,value){byId(id).textContent=value;}
function scoreRows(index){
  const scores=data.baseline.slice();
  if(index===1){
    for(const cid of data.born)scores[cid-1]=0;
    for(const [src,dst,change] of data.edges)scores[src-1]+=change;
  }
  return scores.map((value,i)=>[i+1,value]).filter(row=>row[1]!==null).sort((a,b)=>b[1]-a[1]||a[0]-b[0]);
}
function cell(tr,value,css){
  const td=document.createElement("td");td.textContent=value;if(css)td.className=css;tr.append(td);
}
function render(){
  for(const [id,on] of [["before",snapshot===0],["after",snapshot===1],["l8",capacity===8],["l12",capacity===12]])
    byId(id).setAttribute("aria-pressed",String(on));
  const state=data.commits[snapshot], sorted=scoreRows(snapshot), top=sorted.slice(0,8), [id,score]=top[7];
  if(JSON.stringify(top)!==JSON.stringify(state.top))throw new Error("Frozen top-8 mismatch.");
  const classic=state.policies["classic"+capacity], partial=state.policies["partial"+capacity];
  const body=byId("ranking");body.replaceChildren();
  for(const [rank,[cid,value]] of top.entries()){
    const tr=document.createElement("tr"), change=value-data.baseline[cid-1];
    cell(tr,rank+1);cell(tr,data.files[cid-1],"path");cell(tr,value);cell(tr,snapshot===0?"—":change===0?"0":(change>0?"+":"")+change);body.append(tr);
  }
  put("valid",sorted.length+" candidate IDs ranked · matches the archived top 8");
  put("priorScore",partial.oldEighth[1]);put("eighthScore",score);put("boundScore",partial.upper[0]);
  let why;
  if(capacity===8 && snapshot===1)
    why="parser.py (ID 11) fell from 30 to 29. The stored outside bound was still (29, −11), exactly its new key. No outside ID could outrank it. The variable-prefix method used its previous tail of 30 and fetched one row.";
  else if(capacity===8)
    why="parser.py (ID 11) rose from 29 to 30. Its updated key cleared the saved bound. Both policies retained the eighth file without an ordered read.";
  else
    why="With twelve slots, the updated eighth score ("+score+") cleared the outside bound ("+partial.upper[0]+"). Both policies had enough evidence to return the first eight files.";
  put("reason",why);
  for(const [name,v] of Object.entries({classicWarm:classic.warm,classicRows:classic.rows,partialWarm:partial.warm,partialRows:partial.rows,
        coldProbes:partial.earlierCold,coldRows:partial.earlierColdRows,localCold:partial.cold}))put(name,v);
  byId("source").href="https://github.com/"+data.repo+"/commit/"+state.rev;
}
for(const [id,index] of [["before",0],["after",1]])byId(id).addEventListener("click",()=>{snapshot=index;render();});
for(const [id,n] of [["l8",8],["l12",12]])byId(id).addEventListener("click",()=>{capacity=n;render();});
for(const [src,dst,d] of data.edges.filter(e=>data.files[e[0]-1]==="src/tox/config/cli/parser.py")){
  const el=document.createElement("li");el.textContent=(d>0?"Added importer: ":"Removed importer: ")+data.files[dst-1];byId("edgeList").append(el);
}
render();
</script></body></html>
'''

if __name__=="__main__":
    main()

