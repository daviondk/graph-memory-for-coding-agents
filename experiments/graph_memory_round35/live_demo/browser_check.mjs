import {spawn} from "node:child_process";
import {once} from "node:events";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
import {createHash} from "node:crypto";
import assert from "node:assert/strict";
const dir=path.dirname(fileURLToPath(import.meta.url));
const root="D:/CodexResearch/x20-r35-live-browser";fs.mkdirSync(root,{recursive:true});
const qa=path.join(dir,"qa");fs.mkdirSync(qa,{recursive:true});
const tmp=fs.mkdtempSync(path.join(root,"chrome-"));const browser=spawn(process.env.CHROME_PATH||"C:/Program Files/Google/Chrome/Application/chrome.exe",["--headless=new","--no-first-run","--no-default-browser-check","--disable-gpu","--disable-extensions","--disable-background-networking","--remote-debugging-port=0","--user-data-dir="+tmp,"about:blank"],{windowsHide:true});
let log="";browser.stderr.on("data",b=>log+=b);const wait=n=>new Promise(r=>setTimeout(r,n));const sha=p=>createHash("sha256").update(fs.readFileSync(p)).digest("hex");
async function poll(fn){for(let j=0;j<150;j++){try{const v=await fn();if(v)return v}catch{}await wait(80)}throw Error("Browser condition timed out")}
let ws;
try{
 const host=await poll(()=>log.match(/DevTools listening on ws:\/\/(127\.0\.0\.1:\d+)/)?.[1]);const pg=await poll(async()=>(await(await fetch("http://"+host+"/json/list")).json()).find(v=>v.type==="page"));
 ws=new WebSocket(pg.webSocketDebuggerUrl);await once(ws,"open");let id=0;const pending=new Map(),errors=[],urls=[];
 ws.onmessage=e=>{const x=JSON.parse(e.data);if(x.id){const p=pending.get(x.id);pending.delete(x.id);x.error?p.reject(Error(x.error.message)):p.resolve(x.result)}else if(x.method==="Runtime.exceptionThrown")errors.push(x.params.exceptionDetails.text);else if(x.method==="Network.requestWillBeSent")urls.push(x.params.request.url)};
 const cdp=(method,params={})=>new Promise((resolve,reject)=>{const k=++id;pending.set(k,{resolve,reject});ws.send(JSON.stringify({id:k,method,params}))});
 const js=async expr=>{const x=await cdp("Runtime.evaluate",{expression:expr,returnByValue:true,awaitPromise:true});if(x.exceptionDetails)throw Error(JSON.stringify(x.exceptionDetails));return x.result.value};
 await cdp("Runtime.enable");await cdp("Page.enable");await cdp("Network.enable");const version=(await cdp("Browser.getVersion")).product;
 await cdp("Emulation.setDeviceMetricsOverride",{width:1350,height:980,deviceScaleFactor:1,mobile:false});
 await cdp("Page.navigate",{url:pathToFileURL(path.join(dir,"index.html")).href});await poll(()=>js("document.readyState==='complete'&&document.querySelectorAll('.addresses button').length>0"));
 const orc=JSON.parse(fs.readFileSync(path.join(dir,"ui-oracle.json")));const measured=await js(`(()=>{
  const out={};for(let i=0;i<DATA.cases.length;i++){const c=DATA.cases[i];out[c.q]={};$('cas').value=i;$('cas').dispatchEvent(new Event('change'));for(const pc of cuts){document.querySelector('#cuts button[value="'+pc+'"]').click();
  const v=current(); const got={changed:{added:v.graph.added.length,removed:v.graph.removed.length,stale:v.graph.stale.length}};
  for(const [key,z] of [['exact',v.a],['append',v.b]]){const {picks,used,got:overlap,total,full}=z;const listed=[...$(key).querySelectorAll('.addresses button')].map(b=>Number(b.textContent.split(' · ')[0].substring(1))-1);
  if(String(listed)!==String(picks)||!$(key).querySelector('.num').textContent.endsWith(full?'1':'0'))throw Error('Display differed from computed results');
  got[key]={picks,used,got:overlap,total,full};}out[c.q][pc]=got;}}return out
 })()`);assert.deepEqual(measured,orc);
 const logged=JSON.parse(fs.readFileSync(path.join(dir,"event-oracle.json"))).states;
 const eventChecks=await js(`(async()=>{const results={};for(let i=0;i<DATA.cases.length;i++){$('cas').value=i;$('cas').dispatchEvent(new Event('change'));const c=DATA.cases[i];results[c.q]={};for(const cut of cuts){document.querySelector('#cuts button[value="'+cut+'"]').click();const by={};for(const mode of ['added_events','removed_events']){$('edgeKind').value=mode;$('edgeKind').dispatchEvent(new Event('change'));const rows=[...$('edgeRows').children].map(t=>{const x=[...t.children].map(d=>d.textContent);if(x[2]!=='Передача данных')throw Error('Wrong relation type');return [Number(x[0].slice(1))-1,Number(x[1].slice(1))-1,2,Number(x[3])]});const all=edgesAt(c,cut)[mode];const a=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(all)));by[mode]={count:all.length,first:rows,sha:[...new Uint8Array(a)].map(n=>n.toString(16).padStart(2,'0')).join('')}}results[c.q][cut]=by;}}return results})()`);
 assert.deepEqual(eventChecks,Object.fromEntries(Object.entries(logged).map(([q,s])=>[q,s.cuts])));
 const interactions=await js(`(()=>{const caseUi=$('cas');caseUi.value=1;caseUi.dispatchEvent(new Event('change'));const outcome=$('effect').textContent;
 const chosen=document.querySelector('#append .addresses button');chosen.click();const click=$('detail').textContent.includes(chosen.textContent.split(' · ')[0]);$('edgeFilter').value='one';$('edgeFilter').dispatchEvent(new Event('change'));
 const changed={};for(const mode of ['added_events','removed_events','added','removed','stale']){$('edgeKind').value=mode;$('edgeKind').dispatchEvent(new Event('change'));changed[mode]=$('edgeCount').textContent}
 caseUi.value=0;caseUi.dispatchEvent(new Event('change'));$('edgeFilter').value='all';$('edgeFilter').dispatchEvent(new Event('change'));return {outcome,click,changed};})()`);
 assert(interactions.click&&interactions.outcome.includes('вытеснило'));const desktop=await js("({width:document.documentElement.scrollWidth,cards:[...document.querySelectorAll('.card')].map(x=>x.getBoundingClientRect().width),graph:document.querySelector('canvas').getBoundingClientRect().height})");assert(desktop.width<=1350&&desktop.cards.every(n=>n>400)&&desktop.graph===120);
 fs.writeFileSync(path.join(qa,"desktop.png"),Buffer.from((await cdp("Page.captureScreenshot",{format:"png",captureBeyondViewport:false})).data,"base64"));
 await cdp("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:true});
 const mobile=await js("({width:document.documentElement.scrollWidth,first:document.querySelectorAll('.card')[0].getBoundingClientRect().bottom,second:document.querySelectorAll('.card')[1].getBoundingClientRect().top,overflow:[...document.querySelectorAll('main,section,.card,select,table')].filter(e=>e.getBoundingClientRect().right>390.5).length})");
 assert.equal(mobile.width,390);assert(mobile.second>=mobile.first&&mobile.overflow===0);fs.writeFileSync(path.join(qa,"mobile.png"),Buffer.from((await cdp("Page.captureScreenshot",{format:"png",captureBeyondViewport:false})).data,"base64"));
 assert.deepEqual(errors,[]);assert(!urls.some(u=>/^https?:/.test(u)));
 const result={states:24,event_lists:24,native_per_event_prefixes:161,fresh_graphs:12,version,html:sha(path.join(dir,"index.html")),oracle:sha(path.join(dir,"ui-oracle.json")),program:sha(fileURLToPath(import.meta.url)),remote_requests:0,errors,controls:interactions,desktop,mobile,screenshots:Object.fromEntries(["desktop.png","mobile.png"].map(f=>[f,sha(path.join(qa,f))]))};
 fs.writeFileSync(path.join(dir,"browser-receipt.json"),JSON.stringify(result,null,2)+"\n");console.log(version,'24/24 browser states');
}finally{if(ws)ws.close();browser.kill();}
