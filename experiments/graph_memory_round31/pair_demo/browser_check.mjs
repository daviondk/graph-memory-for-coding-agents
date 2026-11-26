import {spawn} from "node:child_process";
import {once} from "node:events";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
import assert from "node:assert/strict";
const dir=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(process.env.INSPECT_BROWSER_TMP||"D:/CodexResearch/x20-r31-pair-browser");
fs.mkdirSync(root,{recursive:true});
const tmp=fs.mkdtempSync(path.join(root,"chrome-"));
const bin=process.env.CHROME_PATH||"C:/Program Files/Google/Chrome/Application/chrome.exe";
const py=process.env.PYTHON||"python";
const server=spawn(py,["-u","serve.py","--port","0"],{cwd:dir,windowsHide:true});
const browser=spawn(bin,["--headless=new","--no-first-run","--no-default-browser-check","--disable-gpu","--disable-background-networking","--disable-extensions","--remote-debugging-port=0","--user-data-dir="+tmp,"about:blank"],{windowsHide:true});
const watch=s=>{let out="";s.on("data",b=>out+=b);return ()=>out};
const text=watch(server.stdout),logs=watch(browser.stderr);
const sleep=n=>new Promise(r=>setTimeout(r,n));
async function poll(f){for(let k=0;k<100;k++){let v;try{v=await f()}catch{}if(v)return v;await sleep(100)}throw Error("test condition timed out")}
let ws;
try{
 const local=await poll(()=>text().match(/http:\/\/127\.0\.0\.1:\d+\//)?.[0]);
 const debug=await poll(()=>logs().match(/DevTools listening on ws:\/\/(127\.0\.0\.1:\d+)/)?.[1]);
 const page=await poll(async()=>(await(await fetch("http://"+debug+"/json/list")).json()).find(p=>p.type==="page"));
 ws=new WebSocket(page.webSocketDebuggerUrl);await once(ws,"open");const pending=new Map(),exceptions=[], urls=[];let id=0;
 ws.onmessage=e=>{const obj=JSON.parse(e.data);if(obj.id){const p=pending.get(obj.id);pending.delete(obj.id);obj.error?p.reject(Error(obj.error.message)):p.resolve(obj.result)}
 else if(obj.method==="Runtime.exceptionThrown"){exceptions.push(obj.params.exceptionDetails.text)}else if(obj.method==="Network.requestWillBeSent"){urls.push(obj.params.request.url)}};
 const cdp=(method,params={})=>new Promise((resolve,reject)=>{const key=++id;pending.set(key,{resolve,reject});ws.send(JSON.stringify({id:key,method,params}))});
 const js=async expr=>{const r=await cdp("Runtime.evaluate",{expression:expr,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value};
 await cdp("Runtime.enable");await cdp("Page.enable");await cdp("Network.enable");

 const panel=JSON.parse(fs.readFileSync(path.join(dir,"cases.json"))).questions;
 const verified=JSON.parse(fs.readFileSync(path.join(dir,"verification.json")));
 const route=(q,list)=>local+"api/query?"+new URLSearchParams({q,lost:list.join(",")});
 const invalid=[route("unknown",[]),route(panel[0].q,[0,0]),route(panel[0].q,[10]),route(panel[0].q,["bad"])];
 for(const url of invalid)assert.equal((await fetch(url)).status,400);
 const receipt={questions:panel.length,interactive_states_per_mode:{},mobile_width:390,invalid_requests:invalid.length};
 async function ready(){await poll(()=>js("document.body.dataset.ready==='yes' && !!window.viewState"))}
 let offlineHash;
 for(const [mode,url] of [["live",local],["offline",pathToFileURL(path.join(dir,"evidence.html")).href]]){
  const start=urls.length;
  await cdp("Emulation.setDeviceMetricsOverride",{width:1120,height:850,deviceScaleFactor:1,mobile:false});
  await cdp("Page.navigate",{url});await poll(()=>js("location.href==="+JSON.stringify(url)+" && window.viewState?.live==="+(mode==="live")));await ready();
  assert.equal(await js("Array.isArray(cases[0].full)"),mode==="offline");
  assert.equal(await js("document.querySelector('#cases').options.length"),24);
  if(mode==="offline"){
   offlineHash=await js(`(async()=>{
      const before=row,bans=removed;let lines=[];
      try{
       for(row of cases)for(let mask=0;mask<(1<<row.titles.length);mask++){
        removed=new Set(row.titles.map((_,i)=>i).filter(i=>mask&(1<<i)));const s=offline();
        const cert=s.certificate===null?"-":s.certificate.join(".");
        lines.push([row.q,mask,s.winner??-1,cert,+s.tree_fallback,+s.raw_fallback,+s.empty].join("|"));
       }
      }finally{row=before;removed=bans}
      const bytes=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(lines.join("\\n")+"\\n"));
      return [...new Uint8Array(bytes)].map(n=>n.toString(16).padStart(2,"0")).join("");
    })()`);
   assert.equal(offlineHash,verified.all_states_sha256);
  }
  let tested=0;
  async function check(q){
   await ready();const state=await js("window.viewState");
   assert.equal(state.q,q.q);assert.equal(state.live,mode==="live");
   const loss=new Set(state.removed);
   const gold=q.full.find(e=>!loss.has(e>>4)&&!loss.has(e&15))??null;
   assert.equal(state.winner,gold);
   const response=await(await fetch(route(q.q,state.removed))).json();
   for(const k of Object.keys(response))assert.deepEqual(state[k],response[k]);
   const text=await js("document.querySelector('#winner').textContent");
   if(gold===null)assert(text.includes("Fewer than two"));else assert.equal(text,[q.titles[gold>>4],q.titles[gold&15]].join(" + "));
   tested++;return state;
  }
  for(const qi of [0,9,23]){
    const q=panel[qi];await js("document.querySelector('#cases').value="+qi+";document.querySelector('#cases').dispatchEvent(new Event('change'))");
    await check(q);
    for(const button of ["two","third","reset"]){await js("document.getElementById("+JSON.stringify(button)+").click()");await check(q)}
    for(let i=0;i<q.titles.length;i++){await js("document.querySelectorAll('#docs input')["+i+"].click()");await check(q)}
    assert(await js("document.querySelector('#two').disabled && document.querySelector('#third').disabled"));
  }
  await js("document.querySelector('#cases').value=18;document.querySelector('#cases').dispatchEvent(new Event('change'))");await ready();
  const q=panel[18];
  let chosen;for(let i=0;i<q.titles.length;i++)for(let j=i+1;j<q.titles.length;j++)if(q.raw.every(e=>[i,j].includes(e>>4)||[i,j].includes(e&15)))chosen=[i,j];
  assert(chosen);for(const i of chosen){await js("document.querySelectorAll('#docs input')["+i+"].click()");await ready()}
  assert((await check(q)).raw_fallback);
  await js("document.querySelector('#annotation summary').click()");assert(await js("document.querySelector('#annotation').open && document.querySelector('#gold').textContent.length>0"));
  await js("document.querySelector('#lists summary').click()");await poll(()=>js("document.querySelectorAll('#entries li').length>0"));
  assert.equal(await js("document.querySelectorAll('#entries li').length"),q.raw.length+q.tree.length);
  assert(await js("document.querySelectorAll('#entries li.lost').length>0"));
  await js("document.querySelector('#lists summary').click()");
  if(mode==="live"){const shot=await cdp("Page.captureScreenshot",{format:"png"});fs.writeFileSync(path.join(dir,"demo.png"),Buffer.from(shot.data,"base64"))}
  await cdp("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:true});
  assert(await js("document.documentElement.scrollWidth<=390 && document.querySelector('#docs').getBoundingClientRect().width>250"));
  await js("document.querySelector('#reset').click()");await check(q);
  if(mode==="offline")assert.equal(urls.slice(start).filter(u=>/^https?:/.test(u)).length,0);
  receipt.interactive_states_per_mode[mode]=tested;
 }
 assert.equal(exceptions.length,0);receipt.js_errors=exceptions;receipt.offline_all_masks_sha256=offlineHash;
 fs.writeFileSync(path.join(dir,"browser-receipt.json"),JSON.stringify(receipt,null,2)+"\n");console.log(JSON.stringify(receipt));
}finally{
 if(ws)ws.close();browser.kill();server.kill();
 if(path.dirname(path.resolve(tmp))===root && path.basename(tmp).startsWith("chrome-")){
    for(let i=0;i<10;i++){try{fs.rmSync(tmp,{recursive:true,force:true});break}catch{await sleep(220)}}
 }
}
