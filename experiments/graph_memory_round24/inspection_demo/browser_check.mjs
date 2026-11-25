import {spawn} from "node:child_process";
import {once} from "node:events";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
import assert from "node:assert/strict";
const dir=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(process.env.INSPECT_BROWSER_TMP||"D:/CodexResearch/x20-r24-inspection-browser");
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
 const cases=await(await fetch(local+"api/cases")).json();
 assert.equal(cases.length,19);
 const receipt={modes:{},cases:cases.length};
 const ref={};
 for(const s of cases){ref[s.id]={};for(const f of ["short","receiver","sender"])for(const p of ["bm25","first_positive"]){
   ref[s.id][f+"|"+p]=await(await fetch(local+"api/view?"+new URLSearchParams({case:s.id,format:f,policy:p}))).json();
 }}
 for(const mode of ["live","offline"]){
   const dataUrls=urls.length;
   await cdp("Emulation.setDeviceMetricsOverride",{width:1240,height:960,deviceScaleFactor:1,mobile:false});
   await cdp("Page.navigate",{url:mode==="live"?local:pathToFileURL(path.join(dir,"inspection.html")).href});
   await poll(()=>js("document.body?.dataset?.active && document.querySelector('#case').options.length===19"));
   const initial=await js("({id:state.id,active:document.body.dataset.active,gain:document.body.dataset.gain,total:document.body.dataset.total})");
   assert.equal(initial.id,cases[0].id);assert.equal(+initial.gain,ref[initial.id]["sender|first_positive"].metrics.new_gold);
   if(mode==="live"){
       const shot=await cdp("Page.captureScreenshot",{format:"png"});fs.writeFileSync(path.join(dir,"inspection.png"),Buffer.from(shot.data,"base64"));
   }
   let verified=0;
   for(const s of cases){
     await js("(()=>{const box=document.getElementById('case');box.value="+JSON.stringify(s.id)+";box.dispatchEvent(new Event('change'))})()");
     await poll(()=>js("state.id==="+JSON.stringify(s.id)));
     for(const f of ["short","receiver","sender"])for(const p of ["bm25","first_positive"]){
        const actual=await js("(()=>{document.querySelector('#formats [data-key="+f+"]').click();document.querySelector('#policies [data-key="+p+"]').click();return {active:document.body.dataset.active, gain:document.body.dataset.gain,total:document.body.dataset.total,old:document.getElementById('old').textContent, missing:document.getElementById('lost').textContent,sql:document.getElementById('sql').textContent, fields:[...document.getElementById('components').rows].map(r=>[r.cells[0].textContent,r.cells[1].textContent,r.cells[2].textContent]),matrix:document.getElementById('comparison').rows.length,err:document.getElementById('error').textContent}})()");
        const v=ref[s.id][f+"|"+p],m=v.metrics;
        const num=x=>+x.replace(/[^\d-]/g,"");
        assert.equal(actual.active,s.id+"/"+f+"/"+p);assert.equal(+actual.gain,m.new_gold);assert.equal(+actual.total,m.total_wp);
        assert.equal(num(actual.old),m.memory_gold);assert.equal(num(actual.missing),m.missing);assert.equal(actual.matrix,6);assert.equal(actual.err,"");
        assert.deepEqual(actual.fields.map(a=>[+a[0],...a[1].match(/\d+/g).map(Number),num(a[2])]),v.components.map(([e,a,b])=>[e,a,b,b-a]));
        assert.equal(actual.sql,v.sql||"SQL-запрос отсутствует.");verified++;
     }
   }
   await js("document.querySelector('#comparison tr button').click()");
   await poll(()=>js("state.fmt==='short' && state.policy==='bm25'"));
   await cdp("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:true});
   assert(await js("document.documentElement.scrollWidth<=390"));
   if(mode==="offline")assert(urls.slice(dataUrls).every(u=>u.startsWith("file:")||u.startsWith("data:")));
   receipt.modes[mode]={verified_modes:verified,sql_matches:true,all_rendered_component_coordinates_match:true,mobile_width_checked:390};
 }
 const failUrl=new URL("api/view?case=not-real&format=sender&policy=bm25",local);
 assert.equal((await fetch(failUrl)).status,400);
 assert.equal((await fetch(new URL("api/cases",local),{method:"POST"})).status,501);
 assert.equal(exceptions.length,0);
 Object.assign(receipt,{sql_injection_surface:"named routes and bound values",bad_case:400,post_is_disabled:501,exceptions});
 fs.writeFileSync(path.join(dir,"browser-receipt.json"),JSON.stringify(receipt,null,2)+"\n");
 console.log(JSON.stringify(receipt));
}finally{
 if(ws)ws.close();browser.kill();server.kill();
 if(path.dirname(path.resolve(tmp))===root && path.basename(tmp).startsWith("chrome-")){
    for(let i=0;i<10;i++){try{fs.rmSync(tmp,{recursive:true,force:true});break}catch{await sleep(220)}}
 }
}
