import {spawn} from "node:child_process";
import {once} from "node:events";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
import {createHash} from "node:crypto";
import assert from "node:assert/strict";
const dir=path.dirname(fileURLToPath(import.meta.url));
const root="D:/CodexResearch/x20-r34-reader-browser";fs.mkdirSync(root,{recursive:true});
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
 await cdp("Emulation.setDeviceMetricsOverride",{width:1380,height:1060,deviceScaleFactor:1,mobile:false});
 await cdp("Page.navigate",{url:pathToFileURL(path.join(dir,"index.html")).href});await poll(()=>js("document.readyState==='complete'&&document.querySelectorAll('.cand').length>0"));
 const oracle=JSON.parse(fs.readFileSync(path.join(dir,"ui-oracle.json")));const measured=await js("(async()=>{const out={};for(let j=0;j<data.cases.length;j++){const c=data.cases[j];out[c.q]={};for(const mode of ['budget','graph','shape','dense']){const order=ord(c,mode),digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(order.join(',')));const v={orderSHA:[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join(''),budgets:{}};for(const b of [128,255,512,999,1024,2047,2048,2049,3072,4096]){const {used,stop,got,total,full}=measure(c,order,b);v.budgets[b]={used,stop,got,total,full}}out[c.q][mode]=v}}return out})()");
 assert.deepEqual(measured,oracle);
 const interact=await js("(()=>{const steps=[];for(let j=0;j<4;j++){$('guide').click();steps.push([data.cases[state.case].kind,state.mode,$('verdict').textContent,$('coverage').textContent,document.querySelector('.cand[aria-pressed=true]')?.dataset.id])}document.querySelectorAll('#filters button')[2].click();const before=$('counter').textContent;$('next').click();const after=$('counter').textContent;const first=document.querySelector('.cand');first.click();const selected=first.dataset.id==state.selected&&$('address').textContent.includes(data.cases[state.case].nodes[Number(first.dataset.id)].id);$('mode').value='dense';$('mode').dispatchEvent(new Event('change'));const dense=$('parts').textContent.includes('Сходство Dense-FT');$('amount').value='999';$('amount').dispatchEvent(new Event('change'));const budget=$('budget').value;$('case').value=6;$('case').dispatchEvent(new Event('change'));const chosen=data.cases[state.case].kind;$('reset').click();return {steps,before,after,selected,dense,budget,chosen};})()");
 assert.deepEqual(interact.steps.map(v=>v.slice(0,3)),[["win","budget","Полный источник получен"],["win","graph","Полный источник не получен"],["loss","budget","Полный источник не получен"],["loss","graph","Полный источник получен"]]);
 assert(interact.steps.every(v=>v[4]!==null&&v[4]!==undefined));assert.notEqual(interact.before,interact.after);assert(interact.selected&&interact.dense);assert.equal(interact.budget,"999");assert.equal(interact.chosen,"neither");
 const desktop=await js("({hasSelected:!!document.querySelector('.cand[aria-pressed=true]'),width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight,details:document.querySelector('.detail').getBoundingClientRect().top,headers:[...document.querySelectorAll('h1,h2')].map(v=>v.innerText)})");assert(desktop.width>=1360 && desktop.width<=1380);assert(desktop.details<700&&desktop.hasSelected);
 fs.writeFileSync(path.join(qa,"desktop.png"),Buffer.from((await cdp("Page.captureScreenshot",{format:"png",captureBeyondViewport:false})).data,"base64"));
 await cdp("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:true});const mobile=await js("({width:document.documentElement.scrollWidth,control:document.getElementById('mode').getBoundingClientRect().width,overflow:[...document.querySelectorAll('main,article,section,select,.cand,.addr')].filter(e=>e.getBoundingClientRect().right>390.5).length})");assert.equal(mobile.width,390);assert(mobile.control>300);assert.equal(mobile.overflow,0);
 fs.writeFileSync(path.join(qa,"mobile.png"),Buffer.from((await cdp("Page.captureScreenshot",{format:"png",captureBeyondViewport:false})).data,"base64"));
 await js("document.querySelector('.detail').scrollIntoView()");await wait(100);
 fs.writeFileSync(path.join(qa,"mobile-detail.png"),Buffer.from((await cdp("Page.captureScreenshot",{format:"png",captureBeyondViewport:false})).data,"base64"));
 assert.deepEqual(errors,[]);assert(!urls.some(u=>/^https?:/.test(u)));
 const receipt={browser:version,oracle_states:320,case_mode_rankings:32,scenario:interact.steps,controls:["budget","mode","case","filter","page","candidate","guided-tour","reset"],desktop,mobile,remote_requests:0,runtime_exceptions:errors,html:sha(path.join(dir,"index.html")),oracle:sha(path.join(dir,"ui-oracle.json")),script:sha(fileURLToPath(import.meta.url)),screenshots:Object.fromEntries(["desktop.png","mobile.png","mobile-detail.png"].map(f=>[f,sha(path.join(qa,f))]))};
 fs.writeFileSync(path.join(dir,"browser-receipt.json"),JSON.stringify(receipt,null,2)+"\n");console.log(version,receipt.oracle_states,receipt.remote_requests);
}finally{if(ws)ws.close();browser.kill();}