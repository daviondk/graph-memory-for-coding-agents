import {spawn} from "node:child_process";
import {once} from "node:events";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
import assert from "node:assert/strict";
const dir=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(process.env.INSPECT_BROWSER_TMP||"D:/CodexResearch/x20-r32-handoff-browser");
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


 const source=JSON.parse(fs.readFileSync(path.join(dir,"verified.json")));
 const receipt={groups:171,modes:{},offline_queries:0};
 async function ready(){await poll(()=>js("document.body.dataset.ready==='yes'"))}
 for(const [mode,url] of [["live",local],["offline",pathToFileURL(path.join(dir,"handoff.html")).href]]){
  const start=urls.length;await cdp("Emulation.setDeviceMetricsOverride",{width:1120,height:870,deviceScaleFactor:1,mobile:false});
  await cdp("Page.navigate",{url});await poll(()=>js("location.href==="+JSON.stringify(url)+" && document.body.dataset.ready==='yes'"));
  assert.equal(await js("document.querySelector('#cases').options.length"),171);let checked=0;
  async function validate(){await ready();const s=await js("window.view");
   const p={q:s.g,read:s.method,budget:s.budget};if(s.idx!==null)p.idx=s.idx;
   const bounds=await js("[$('lo').value,$('hi').value]");if(bounds[0])p.start=bounds[0];if(bounds[1])p.end=bounds[1];
   const direct=await(await fetch(local+"api/open?"+new URLSearchParams(p))).json();
   assert.deepEqual(s.hits,direct.hits);assert.equal(s.cost,direct.read_wp);assert.equal(await js("document.querySelectorAll('#lines tr').length"),direct.rows.length);checked++;return s}
  for(const name of ["boundary","forward","unavailable","versions"]){
    await js("document.querySelector('[data-preset="+name+"]').click()");await poll(()=>js("window.view.g==="+JSON.stringify(source.presets[name])+" && document.body.dataset.ready==='yes'"));
    const s=await validate();if(name==="boundary")assert.deepEqual(s.hits.slice(0,2),[true,true]);if(name==="forward")assert.deepEqual(s.hits.slice(2),[true,true]);
    if(name==="unavailable")assert.equal(s.idx,null);
  }
  await js("document.querySelector('#address').selectedIndex=1;document.querySelector('#address').dispatchEvent(new Event('change'))");await validate();
  await js("$('budget').value='64';$('budget').dispatchEvent(new Event('change'))");assert((await validate()).cost<=64);
  await js("$('lo').value='5';$('hi').value='12';$('hi').dispatchEvent(new Event('change'))");await validate();
  await js("$('hi').value='4';$('hi').dispatchEvent(new Event('change'))");assert.equal(await js("document.body.dataset.ready"),"invalid");
  await js("document.querySelector('[data-preset=boundary]').click()");await ready();await validate();
  if(mode==="live"){
   await js("$('inspect').open=true");const shot=await cdp("Page.captureScreenshot",{format:"png"});fs.writeFileSync(path.join(dir,"demo.png"),Buffer.from(shot.data,"base64"));
  }else{
   const queryStats=await js(`(()=>{const saved=record;let counts=[0,0,0,0],total=0;for(const r of Object.values(bundle.details)){record=r;let a=r.addresses.find(x=>x.idx===r.routed);for(const [j,m] of ["forward","boundary"].entries()){const v=offlineOpen(a,m,512,null,null);counts[2*j]+=Number(v.hits[0]&&v.hits[1]);counts[2*j+1]+=Number(v.hits[2]&&v.hits[3]);total++}}record=saved;return {counts,total}})()`);
   assert.deepEqual(queryStats,{counts:[0,4,48,0],total:342});receipt.offline_queries=queryStats.total;
   assert.equal(urls.slice(start).filter(u=>/^https?:/.test(u)).length,0);
  }
  await cdp("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:true});
  assert(await js("document.documentElement.scrollWidth<=390 && $('cases').getBoundingClientRect().width>260"));
  receipt.modes[mode]=checked;
 }
 assert.deepEqual(exceptions,[]);receipt.exceptions=exceptions;receipt.mobile_width=390;fs.writeFileSync(path.join(dir,"browser-receipt.json"),JSON.stringify(receipt,null,2)+"\n");console.log(receipt);
}finally{
 if(ws)ws.close();browser.kill();server.kill();
 if(path.dirname(path.resolve(tmp))===root && path.basename(tmp).startsWith("chrome-")){
    for(let i=0;i<10;i++){try{fs.rmSync(tmp,{recursive:true,force:true});break}catch{await sleep(220)}}
 }
}
