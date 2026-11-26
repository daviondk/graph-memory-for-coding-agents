"use strict";
const $ = id => document.getElementById(id);
const labels = {growth:"File expansion",contraction:"File contraction",capacity:"Capacity overflow"};
const reason = {replaced:"inside the edited span, with no informative receipt fact",unobserved:"no prior or receipt observation maps here",evicted:"omitted by the global 128-fact limit"};
let active=null, sourceVersion=0, requestVersion=0;
function node(tag,text,cls){const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e}
function row(parent,values){const tr=node("tr","");for(const x of values){const td=node("td","");if(x instanceof Node)td.append(x);else td.textContent=x;tr.append(td)}parent.append(tr)}
function range(a,b){return a===b?String(a):a+"–"+b}
function hash(text){const e=node("span",text.slice(0,12)+"…","hash");e.title=text;return e}
function sourceTable(id,rows){const parent=$(id);parent.replaceChildren();for(const [n,s] of rows){const r=node("div","","obsrow");r.append(node("span",n),hash(s));parent.append(r)}}
async function json(path,params={}){const q=new URLSearchParams(params).toString();const response=await fetch(path+(q?"?"+q:""),{cache:"no-store"});const data=await response.json();if(!response.ok)throw Error(data.error||"Request failed");return data}
function setRange(v){$("lo").value=v[0];$("hi").value=v[1]}
function showError(err){$("error").textContent=err.message;$("status").textContent="Request failed"}
function render(result){
  $("matched").textContent=result.rows.length;$("window").textContent=range(result.lo,result.hi);
  const comp=$("comparison"),digests=$("digests");comp.replaceChildren();digests.replaceChildren();
  const names={eager_index:"Materialized index",inverse:"Inverse range"};
  for(const [method,count] of Object.entries(result.stats)){
    row(comp,[names[method],count.db_rows,count.hash_bytes]);
    digests.append(node("div",names[method]+" · "+count.answer_digest));
  }
  $("status").textContent="Signatures match";$("mode").textContent=result.overflow?
    "Capacity fallback. The inverse reader retrieves the whole candidate set, applies the global 128-fact rule, then filters to the requested lines.":
    "Range lookup. The inverse reader maps the requested coordinates to old line intervals and overlays the editor receipt.";
  $("rows").replaceChildren();for(const item of result.rows){
    const origin=item.origin==="receipt"?"Editor receipt":(item.origin==="shifted"?"Shifted from ":"Previous view, line ")+item.before;
    row($("rows"),[item.n,node("span",origin,"origin"),hash(item.hash)]);
  }
  $("empty").hidden=Boolean(result.rows.length);const gaps=$("gaps");gaps.replaceChildren();
  if(!result.gaps.length)gaps.append(node("span","Every requested line is present.","muted"));
  for(const g of result.gaps){const r=node("div","","gap");r.append(node("b",range(g.lo,g.hi)),document.createTextNode(" · "+reason[g.reason]));gaps.append(r)}
  document.documentElement.dataset.window=[result.case,result.lo,result.hi].join("/");
}
async function requestRange(){
  if(!active)return;const version=++requestVersion, which=active.label;
  $("error").textContent="";$("status").textContent="Querying SQLite…";
  try{const result=await json("/api/read",{case:which,lo:$("lo").value,hi:$("hi").value});
      if(version===requestVersion && active?.label===which)render(result)}
  catch(err){if(version===requestVersion)showError(err)}
}
async function selectCase(id){
  const v=++sourceVersion;++requestVersion;active=null;$("error").textContent="";$("status").textContent="Reading observation…";
  try{
    const c=await json("/api/source",{case:id});if(v!==sourceVersion)return;active=c;
    for(const b of $("cases").children)b.setAttribute("aria-pressed",String(b.dataset.key===id));
    $("issue").textContent=c.issue.replace("__"," / ");$("zone").textContent=c.zone==="main_strict"?"Primary · strict":"Additional · opaque";
    $("oldrange").textContent=range(c.start,c.end);$("delta").textContent=(c.delta>0?"+":"")+c.delta+" lines";$("file").textContent=c.path_id.slice(0,12);
    $("base-title").textContent="Previous view · "+c.base.length+" retained facts";
    $("receipt-title").textContent="Editor receipt · "+c.receipt.length+" facts";
    sourceTable("base",c.base);sourceTable("receipt",c.receipt);
    $("special").textContent=c.overflow?"Evicted line":"Edited region";setRange(c.requested);await requestRange()
  }catch(err){if(v===sourceVersion)showError(err)}
}
$("range").addEventListener("submit",ev=>{ev.preventDefault();requestRange()});
$("actual").addEventListener("click",()=>{if(active){setRange(active.requested);requestRange()}});
$("special").addEventListener("click",()=>{if(active){setRange(active.special);requestRange()}});
(async()=>{try{const cases=await json("/api/cases");for(const c of cases){const b=node("button",labels[c.label]);b.dataset.key=c.label;b.setAttribute("aria-pressed","false");b.addEventListener("click",()=>selectCase(c.label));$("cases").append(b)}await selectCase(cases[0].label)}catch(err){showError(err)}})();
