"""Render the 54 versioned edit2ripple rankings and their raw Git witnesses as an offline file."""
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "graph_memory_round54/code_links"
DEFAULT = "a726f272e7ddbd50bac4face"
EXAMPLES = [DEFAULT,"d6dbe66e15d389619fb51499","0631449332f969f725276ef8","0150e5de390fa7c521175b89"]


def read(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes())


def records():
    seal = read(HERE/"expanded-seal.json")
    assert all(hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest for name,digest in seal.items())
    projected = read(HERE/"expanded-ranks.json.gz")
    history = read(HERE/"history.json.gz")
    first = read(SOURCE/"forecasts.json.gz")
    truth = read(SOURCE/"graded-rows.json.gz")
    assert set(first) == set(projected) == set(truth) and len(first) == 54
    out = {}
    for q,row in projected.items():
        anchor = first[q]["anchor"]
        lexical, selected = row["ranked"]["lexical"], row["ranked"]["corroborated"]
        assert lexical[:4] == selected[:4] and row["base"] == first[q]["commit"]
        candidates = []
        for p,count,agreed,weight,last in row["evidence"]:
            witnesses = []
            for age,(sha,m,paths) in enumerate(history[row["base"]]["history"]):
                if 2<=m<=20 and anchor in paths and p in paths:
                    also = [f for f in lexical[:4] if f in paths]
                    witnesses.append(dict(sha=sha, age=age, size=m, also=also))
            total = sum((Fraction(1,w["size"]-1) for w in witnesses), Fraction())
            assert len(witnesses) == count and sum(bool(w["also"]) for w in witnesses)==agreed
            assert witnesses[0]["age"]==last and abs(float(total)-weight)<1e-10
            candidates.append(dict(path=p,count=count,agreed=agreed,weight=str(total),witness=witnesses))
        qualified = [c for c in candidates if c["count"]>=2 or c["agreed"]>0]
        assert selected[-1] == (qualified[0]["path"] if qualified else lexical[-1])
        out[q] = dict(repo=row["repo"],base=row["base"],anchor=anchor,
                      lexical=lexical,graph=selected,evidence=candidates,reference=truth[q]["gold"],
                      depth=len(history[row["base"]]["history"]),available=row["available"])
    return out


HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Git evidence for a fifth file</title>
<style>
*{box-sizing:border-box}html{font-family:Inter,"Segoe UI",Arial,sans-serif;color:#142f31;background:#f4f4ef;line-height:1.4}body{margin:0}main{max-width:1160px;margin:auto;padding:24px 32px}.top{display:flex;align-items:baseline;gap:20px;justify-content:space-between}.top p{font-size:.82rem;color:#425e59}.top p,.intro,h1,h2,h3,p{margin:0}h1{font:normal clamp(2.1rem,3.5vw,3.25rem)/1.06 Georgia,serif;letter-spacing:-.045em}.intro{color:#47615f;margin:7px 0 16px;font-size:1rem}.selection{border-block:1px solid #c7d3cb;padding:12px 0;display:grid;grid-template-columns:minmax(230px,1.1fr) minmax(350px,1fr);gap:20px;align-items:end}.label,legend{display:block;font-size:.77rem;font-weight:700;color:#35534e;margin-bottom:4px}select,button{font:inherit}select{width:100%;font-size:.9rem;min-height:38px;border:1px solid #a7b9ac;border-radius:5px;padding:3px 8px;color:#173b35;background:white}button{color:#24443d;background:white;border:1px solid #b5c5ba;border-radius:5px;padding:7px 10px;font-size:.84rem;cursor:pointer}.examples{display:flex;gap:5px;flex-wrap:wrap}button:hover,button:focus-visible,select:focus-visible{outline:2px solid #618e7c;outline-offset:1px}.session{padding:15px 0 12px}.session h2{font-size:1.1rem;line-height:1.3}.mono,code{font-family:Consolas,"Courier New",monospace;overflow-wrap:anywhere}.session .meta{color:#4c665f;margin-top:4px;font-size:.76rem}.control{display:flex;align-items:end;justify-content:space-between;gap:15px;flex-wrap:wrap;margin:0 0 11px}.seg{display:flex;gap:0}.seg button{border-radius:0;padding:6px 13px}.seg button:first-child{border-radius:5px 0 0 5px}.seg button:last-child{border-radius:0 5px 5px 0;margin-left:-1px}.seg button[aria-pressed=true]{background:#205d49;color:white;border-color:#205d49}.grid{display:grid;grid-template-columns:1fr 1.05fr;gap:14px;align-items:start}.panel{padding:15px 16px;background:#fff;border:1px solid #c8d4cb;border-radius:7px;min-width:0}.panel h2{font-size:1.05rem}.panel h3{font-size:.85rem;margin:10px 0 4px}.panel p{font-size:.87rem}.rank{padding:0;margin:8px 0 0;list-style:none;counter-reset:files}.rank li{counter-increment:files;display:flex;gap:10px;align-items:baseline;padding:7px 5px;border-top:1px solid #dfe6df}.rank li:before{content:counter(files);font-family:Consolas,monospace;color:#577268;font-size:.82rem;min-width:12px}.rank li:last-child{background:#e7f1e8;border-left:3px solid #5d8d72;padding-left:3px}.rank code,.panel code{font-size:.79rem}.hit{font-style:normal;color:#246136;font-size:.72rem;margin-left:auto;white-space:nowrap}.disposition{color:#37584b;margin:8px 0 4px!important}.witness{padding:8px 0 7px;border-top:1px solid #dfe6df}.witness+.witness{margin-top:5px}.witness .hash{color:#275344;font-size:.76rem;display:block}.witness small{font-size:.77rem;color:#547067}.reason{background:#f1f5ee;padding:8px 10px;margin:6px 0!important;color:#314b40}.clip{display:block;margin:4px 0;color:#526a63;font-size:.79rem}.reference{background:#fffaf0;border:1px solid #d2cbb6;border-radius:6px;padding:12px 15px;margin-top:12px}.reference h2{font-size:1rem}.reference ul{margin:6px 0 0;padding-left:19px}.reference li{font-size:.8rem}.footer{border-top:1px solid #c5d0c5;margin-top:15px;padding-top:8px;color:#50635d;font-size:.76rem}.footer summary{cursor:pointer}details p{margin-top:5px}.secondary{margin-top:8px}.secondary select{font: .78rem Consolas,monospace;min-height:27px}.visually-hidden{position:absolute;clip:rect(0,0,0,0);height:1px;width:1px;overflow:hidden}.nospace{margin:0}[hidden]{display:none}
@media(max-width:760px){main{padding:17px 13px}.top{display:block}.top p{margin-top:3px}.selection,.grid{grid-template-columns:1fr;gap:8px}.intro{font-size:.9rem}.rank li{padding-block:5px}.session{padding:10px 0}.panel{padding:10px 12px}.control{gap:8px}.clip{word-break:break-word}}
</style></head><body><main>
<header class="top"><h1>Git evidence for a fifth file</h1><p>Agent Retrieval Bench · edit2ripple</p></header>
<p class="intro">An edit supplies one anchor file. The agent can read five other files. Inspect the Git commits that can change its last choice.</p>
<section class="selection" aria-label="Task selection"><div><label for="task" class="label">Task · 54 archived cases</label><select id="task"></select></div>
<div><span class="label">Example anchors</span><div class="examples" id="examples"></div></div></section>
<section class="session"><h2>Anchor <code id="anchor"></code></h2><p class="meta"><span id="repo"></span> · base <code id="base"></code></p></section>
<div class="control"><div role="group" aria-label="Retrieval policy" class="seg"><button id="lexical" type="button">Lexical</button><button id="graph" type="button">Git corroboration</button></div><button id="reveal" type="button" aria-controls="reference" aria-expanded="false">Reveal reference files</button></div>
<div class="grid"><section class="panel"><h2>Files to read</h2><ol class="rank" id="rank"></ol><p class="disposition" id="decision"></p></section>
<section class="panel"><h2>Historical evidence</h2><div id="evidence"></div></section></div>
<section class="reference" id="reference" hidden><h2>Retrospective reference</h2><p id="hits"></p><ul id="gold"></ul></section>
<footer class="footer"><p id="budget-note">__BUDGET__</p><details><summary>Method and limits</summary><p>Both policies preserve the first four lexical results. The history policy considers files outside the lexical top 20 that exist at the task’s base commit. A candidate qualifies after two shared commits or a shared commit with one of the first four results. Each witness contributes 1/(m−1), where m counts added or modified paths. Larger total weight wins, followed by more corroborated commits, recency and path order.</p><p>Each case uses up to 64 pre-existing first-parent transitions including the base. Commits with 2–20 non-deleted paths provide evidence. The reference comes from the benchmark and is hidden until requested. This replay measures file retrieval on a previously studied panel. It does not execute a coding agent or measure completed fixes. All paths and evidence are embedded for offline use.</p></details></footer>
<script type="application/json" id="records">__DATA__</script>
<script>
"use strict";
const runs = JSON.parse(document.getElementById("records").textContent);
const el = id => document.getElementById(id);
const create = (tag, text, cls) => {const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls;return n};
const option = (id, label) => {const opt=create("option",label);opt.value=id;return opt};
const examples = __EXAMPLES__, brief=["Caddy · TLS","etcd · embed","Caddy · parser","gin · binding"];
let id=examples[0], policy="graph", shown=false, inspect=0;
const ordered=Object.keys(runs).sort((a,b)=>runs[a].repo.localeCompare(runs[b].repo)||runs[a].anchor.localeCompare(runs[b].anchor)||a.localeCompare(b));
for(const key of ordered){const r=runs[key];el("task").append(option(key,r.repo+" · "+r.anchor+" · "+key.slice(0,6)))}
examples.forEach((key,i)=>{const b=create("button",brief[i]);b.type="button";b.onclick=()=>choose(key);el("examples").append(b)});
function choose(key){id=key;shown=false;inspect=0;render()}
el("task").onchange=()=>choose(el("task").value);
for(const k of ["lexical","graph"]){el(k).onclick=()=>{policy=k;inspect=0;render()}}
el("reveal").onclick=()=>{shown=!shown;render()};
function drawEvidence(r){
 const target=el("evidence");target.replaceChildren();
 if(policy==="lexical"){target.append(create("p","The lexical policy takes the fifth file from its published ranked list.","reason"));return}
 const qualified=x=>x.count>=2||x.agreed>0;
 const winner=r.evidence.find(qualified);
 if(!r.evidence.length){target.append(create("p","No file outside the lexical top 20 shared an eligible historical commit with the anchor.","reason"));return}
 const shownRows=winner?[winner,...r.evidence.filter(c=>c!==winner)]:r.evidence;
 const focus=shownRows[inspect]||shownRows[0];
 const line=create("div");line.className="secondary";const lbl=create("label","Inspect outside-shortlist candidate","label");lbl.htmlFor="candidate";const menu=create("select");menu.id="candidate";shownRows.forEach((x,i)=>menu.append(option(String(i),x.path)));menu.value=String(inspect);menu.onchange=()=>{inspect=Number(menu.value);render()};line.append(lbl,menu);target.append(line);
 let why=focus.agreed>0?focus.agreed+" corroborated "+(focus.agreed===1?"commit":"commits"):"no corroborating top-four file";
 if(focus.count>=2)why=focus.count+" shared commits and "+why;
 const reason=(qualified(focus)?"Qualifies with ":"Below threshold with ")+why+". Total weight "+focus.weight+".";
 target.append(create("p",reason,"reason"));
 for(const w of focus.witness){
   const block=create("div",undefined,"witness");const sha=create("code",w.sha,"hash");block.append(sha,create("small",w.age+" first-parent steps before base · "+w.size+" changed paths · vote 1/"+(w.size-1)));
   if(w.also.length){block.append(create("small","Corroborating top-four files","clip"));for(const a of w.also)block.append(create("code",a,"clip"))}
   target.append(block);
 }
}
function render(){
 const r=runs[id];el("task").value=id;el("anchor").textContent=r.anchor;el("repo").textContent=r.repo;el("base").textContent=r.base;
 for(const k of ["lexical","graph"])el(k).setAttribute("aria-pressed",String(policy===k));
 const list=r[policy];el("rank").replaceChildren();for(const p of list){const li=create("li");li.append(create("code",p));if(shown&&r.reference.includes(p))li.append(create("em","reference","hit"));el("rank").append(li)}
 const changed=r.graph[4]!==r.lexical[4];
 el("decision").textContent=policy==="lexical"?"Five files from the published lexical ranking.":changed?"The top four stay in place. Git evidence replaces the fifth lexical file.":"The fifth lexical file stays in place. No outside candidate qualifies.";
 drawEvidence(r);
 el("reference").hidden=!shown;el("reveal").textContent=shown?"Hide reference files":"Reveal reference files";el("reveal").setAttribute("aria-expanded",String(shown));
 el("gold").replaceChildren();el("hits").textContent="";
 if(shown){const count=list.filter(p=>r.reference.includes(p)).length;el("hits").textContent="Retrieved "+count+" of "+r.reference.length+" annotated files with five reads.";for(const p of r.reference){const li=create("li");li.append(create("code",p));el("gold").append(li)}}
}
render();
</script></main></body></html>'''


def main():
    source = records()
    payload = json.dumps(source,separators=(",",":"),ensure_ascii=True).replace("<","\\u003c")
    extra = read(HERE/"expanded-results.json")["means"]
    original = read(HERE/"original-results.json")
    limits = (f"Across 54 tasks, five additional reads give Recall@5 of {100*extra['corroborated'][0]:.2f}% with Git evidence and "
              f"{100*extra['lexical'][0]:.2f}% with lexical retrieval. The published five-slot budget counts a returned anchor. "
              f"Under that budget the same rule scores {100*original['means']['graph'][0]:.2f}% versus "
              f"{100*original['means']['lexical'][0]:.2f}% for lexical retrieval ({100*original['primary']['delta']:.2f} percentage points).")
    page = HTML.replace("__DATA__",payload).replace("__EXAMPLES__",json.dumps(EXAMPLES)).replace("__BUDGET__",limits)
    (HERE/"replay.html").write_bytes((page+"\n").encode())
    print("Embedded",len(source),"tasks;",len(page),"characters")


if __name__=="__main__":
    main()
