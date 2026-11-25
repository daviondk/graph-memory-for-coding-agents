import {spawn} from "node:child_process";
import {once} from "node:events";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
import assert from "node:assert/strict";
const dir=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(process.env.INSPECT_BROWSER_TMP||"D:/CodexResearch/x20-r28-inspection-browser");
fs.mkdirSync(root,{recursive:true});
const tmp=fs.mkdtempSync(path.join(root,"chrome-"));
const bin=process.env.CHROME_PATH||"C:/Program Files/Google/Chrome/Application/chrome.exe";
const py=process.env.PYTHON||"python";
const server=spawn(py,["-u","serve_demo.py","--port","0"],{cwd:dir,windowsHide:true});
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
 const cases=await(await fetch(local+"api/cases")).json();assert.equal(cases.length,96);
 await cdp("Emulation.setDeviceMetricsOverride",{width:1100,height:810,deviceScaleFactor:1,mobile:false});
 await cdp("Page.navigate",{url:local});
 await poll(()=>js("document.querySelector('#cases')?.options.length===96 && document.querySelector('#counts')?.textContent.length>0"));
 const initial=await js("document.querySelector('#cases').value");let checked=0;
 const ids=[initial,cases.find(x=>!x.diff).q,cases[95].q];
 for(const id of ids){
  await js("document.querySelector('#cases').value="+JSON.stringify(id)+";document.querySelector('#cases').dispatchEvent(new Event('change'))");
  await poll(()=>js("data?.q==="+JSON.stringify(id)));
  for(const preset of ['record','winner','random']){
   const v=await js("data.presets["+JSON.stringify(preset)+"]");
   await js("document.querySelector('#presets').value="+JSON.stringify(preset)+";document.querySelector('#presets').dispatchEvent(new Event('change'))");
   await poll(()=>js("String(data.cut)==="+JSON.stringify(String(v))));
   const api=await(await fetch(local+"api/read?"+new URLSearchParams({q:id,start:v[0],end:v[1]}))).json();
   const display=await js("document.querySelector('#fixed').textContent");
   if(api.fixed)assert(display.includes('['+api.fixed.range.join(', ')+')'));checked++;
  }
 }
 await js("document.querySelector('#lo').value='0';document.querySelector('#hi').value='2147483647';document.querySelector('#form').requestSubmit()");
 await poll(()=>js("document.querySelector('#fixed').textContent.includes('не осталось')"));
 await js("document.querySelector('#cases').value="+JSON.stringify(initial)+";document.querySelector('#cases').dispatchEvent(new Event('change'))");
 await poll(()=>js("data?.q==="+JSON.stringify(initial)+" && data.physically_measured"));
 if(await js("!document.querySelector('#reference').hidden")){await js("document.querySelector('#reference summary').click()");assert(await js("document.querySelector('#reference').open && document.querySelector('#gold').textContent.length>0"))}
 const shot=await cdp("Page.captureScreenshot",{format:"png"});fs.writeFileSync(path.join(dir,"demo.png"),Buffer.from(shot.data,"base64"));
 await cdp("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:true});
 assert(await js("document.documentElement.scrollWidth<=390"));
 assert.equal(exceptions.length,0);
 const receipt={questions:cases.length,interactive_checks:checked,custom_empty:true,mobile_width:390,js_errors:exceptions};
 fs.writeFileSync(path.join(dir,"browser-receipt.json"),JSON.stringify(receipt,null,2)+"\n");console.log(JSON.stringify(receipt));
}finally{
 if(ws)ws.close();browser.kill();server.kill();
 if(path.dirname(path.resolve(tmp))===root && path.basename(tmp).startsWith("chrome-")){
    for(let i=0;i<10;i++){try{fs.rmSync(tmp,{recursive:true,force:true});break}catch{await sleep(220)}}
 }
}
