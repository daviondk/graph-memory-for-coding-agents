// Standalone headless smoke test. Set CHROME_PATH to a Chromium browser executable.
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';

const dir=path.dirname(fileURLToPath(import.meta.url));
const temp=fs.mkdtempSync(path.join(process.env.PROVENANCE_TEST_TMP||os.tmpdir(),'evidence-browser-'));
const chrome=process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe';
const python=process.env.PYTHON||'python';
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function poll(fn){for(let i=0;i<160;i++){let v;try{v=await fn()}catch{} if(v)return v;await pause(100)}throw Error('Timed out waiting for a local test condition')}
function collect(stream){let s='';stream.on('data',b=>s+=b);return ()=>s}

const server=spawn(python,['-u','serve.py','--port','0'],{cwd:dir,windowsHide:true});
const messages=collect(server.stdout);
const browser=spawn(chrome,['--headless=new','--disable-extensions','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+temp,'about:blank'],{windowsHide:true});
const logs=collect(browser.stderr);let ws,call;
try{
    const url=await poll(()=>messages().match(/http:\/\/127\.0\.0\.1:\d+\//)?.[0]);
    const debugging=await poll(()=>logs().match(/DevTools listening on ws:\/\/(127\.0\.0\.1:\d+)/)?.[1]);
    const offline=process.argv.includes('--offline');
    const page=await poll(async()=> (await (await fetch('http://'+debugging+'/json/list')).json()).find(x=>x.type==='page'));
    ws=new WebSocket(page.webSocketDebuggerUrl);await once(ws,'open');
    let seq=0;const waiting=new Map(),exceptions=[];
    ws.onmessage=e=>{const obj=JSON.parse(e.data);
        if(obj.id){const p=waiting.get(obj.id);waiting.delete(obj.id);if(p)obj.error?p.reject(Error(JSON.stringify(obj.error))):p.resolve(obj.result)}
        else if(obj.method==='Runtime.exceptionThrown'){exceptions.push(obj.params.exceptionDetails.text)}};
    call=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;waiting.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
    const js=async expr=>{const r=await call('Runtime.evaluate',{expression:expr,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value};
    await call('Runtime.enable');await call('Page.enable');
    await call('Emulation.setDeviceMetricsOverride',{width:1160,height:860,deviceScaleFactor:1,mobile:false});
    await call('Page.navigate',{url:offline?pathToFileURL(path.join(dir,'explorer.html')).href:url});
    await poll(()=>js('document.querySelector("#trace")?.options.length===96 && document.querySelector("#rows")?.children.length>0'));
    const checkTotals=async()=>{
        const v=await js("({id:document.querySelector('#trace').value,step:document.querySelector('#step').value,stats:['exact','append','final'].map(k=>document.getElementById(k).textContent),position:document.querySelector('#position').textContent})");
        const snap=await(await fetch(url+'api/view?'+new URLSearchParams({t:v.id,step:v.step}))).json();
        return ['exact','append','final'].every((k,i)=>Number(v.stats[i])===snap.edges.filter(e=>e[k]).length)&&v.position.startsWith('Event '+(snap.step+1)+' /')
    };
    await poll(checkTotals);
    await js("document.querySelector('#stops button:nth-child(2)').click()");
    await poll(checkTotals);
    await js("document.querySelector('#filter').value='stale';document.querySelector('#filter').dispatchEvent(new Event('change'))");
    await poll(()=>js("document.querySelectorAll('#rows tr').length>0 && [...document.querySelectorAll('#rows tr td:nth-child(2)')].every(x=>x.textContent==='Revoked') && document.querySelector('#ledger').children.length>0"));
    const stale=await js("document.querySelectorAll('#rows tr').length");
    await js("document.querySelector('#rows tr:last-child button').click()");
    await poll(()=>js("document.querySelector('#detailTitle').textContent.includes('→')&&document.querySelector('#ledger').children.length>0"));
    await js("document.querySelector('#example').click()");await poll(checkTotals);
    await poll(()=>js("document.querySelector('#detailTitle').textContent==='Output 14 → call 19' && document.querySelector('#ledger').textContent.includes('also produced by output')"));
    const reasonCount=await js("document.querySelector('#ledger').children.length");assert(reasonCount>=3);
    const screenshot=await call('Page.captureScreenshot',{format:'png'});
    if(!offline)fs.writeFileSync(path.join(dir,'explorer.png'),Buffer.from(screenshot.data,'base64'));
    await js("document.querySelector('#forward').click()");await poll(checkTotals);
    await js("document.querySelector('#back').click()");await poll(checkTotals);
    await js("document.querySelector('#trace').selectedIndex=21;document.querySelector('#trace').dispatchEvent(new Event('change'))");await poll(checkTotals);
    await call('Emulation.setDeviceMetricsOverride',{width:390,height:840,deviceScaleFactor:1,mobile:true});
    assert(await js("document.documentElement.scrollWidth <= 390"));
    await js("document.querySelector('#step').value=0;document.querySelector('#step').dispatchEvent(new Event('input'))");
    await poll(()=>js("document.querySelector('#back').disabled && document.querySelector('#rows').children.length===0"));
    assert.equal((await fetch(url+'api/view?t=unknown&step=0')).status,400);assert.equal(exceptions.length,0);
    if(offline){
        const audit=await js(`(async()=>{const all=await fetchJSON('/api/cases'),result=[];for(const c of all){const v=await fetchJSON('/api/view?'+new URLSearchParams({t:c.t,step:0}));for(const ck of v.checkpoints){const s=await fetchJSON('/api/view?'+new URLSearchParams({t:c.t,step:ck.step}));result.push({t:c.t,step:ck.step,edges:s.edges})}}return result})()`);
        assert.equal(audit.length,383);
        for(const c of audit){const s=await(await fetch(url+'api/view?'+new URLSearchParams({t:c.t,step:c.step}))).json();assert.deepEqual(c.edges,s.edges)}
    }
    fs.writeFileSync(path.join(dir,offline?'offline-receipt.json':'browser-receipt.json'),JSON.stringify({cases:96,offline_all_383_checkpoints_rechecked:offline,default_history_stale_rows_at_second_checkpoint:stale,checkpoint_counts_match_sql:true,filters:true,edge_details:true,history_switch:true,guided_example_and_producer_reason:true,forward_backward:true,zero_view:true,narrow_viewport_no_overflow:true,invalid_request:400,script_exceptions:exceptions},null,2)+'\n');
    console.log('Browser checks passed, stale links',stale);
}finally{
    if(ws)ws.close();
    browser.kill();server.kill();
    // Only the test-created directory may be removed. Chromium can briefly hold files on Windows.
    if(path.basename(temp).startsWith('evidence-browser-')){for(let i=0;i<15;i++){try{fs.rmSync(temp,{recursive:true,force:true});break}catch{await pause(200)}}}
}
