"""Exercise all scenarios and ensure the normal request never reads hash witnesses."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

D=Path(__file__).resolve().parent

def run(screenshot=None):
    server=subprocess.Popen([sys.executable,'-B','-u',str(D/'app.py'),'--port','0'],stdout=subprocess.PIPE,text=True)
    address=server.stdout.readline().strip();assert address.startswith('http://127.0.0.1:')
    errors=[];remote=[];hits=[];observation={}
    try:
        with sync_playwright() as pw:
            exe=os.environ.get('BROWSER_EXE') or next(str(p) for p in (Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')) if p.is_file())
            b=pw.chromium.launch(executable_path=exe,headless=True,args=['--disable-background-networking'])
            ctx=b.new_context(viewport={'width':1240,'height':945},device_scale_factor=1)
            def filter_requests(route):
                u=urlsplit(route.request.url)
                if u.hostname=='127.0.0.1':hits.append(u.path);route.continue_()
                else:remote.append(u.hostname);route.abort()
            ctx.route('**/*',filter_requests);page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(address)
            for i,case in enumerate(('relocated','changed','stale')):
                if i:page.select_option('#case',case)
                page.wait_for_function("(v)=>document.body.dataset.ready===v",arg=case)
                assert hits.count('/api/audit')==i and 'have not been opened' in page.locator('#result').inner_text()
                assert page.locator('#fileDecision').inner_text()=='Packet changes'
                assert page.locator('#spanDecision').inner_text()==('Packet changes' if case=='changed' else 'Reuse original IDs')
                assert 'Open audit' in page.locator('#blocks').inner_text()
                page.select_option('#filter','all');total=page.locator('#blocks tr').count();page.select_option('#filter','intersect');overlap=page.locator('#blocks tr').count()
                page.select_option('#filter','selected');page.locator('#blocks button').first.click();assert hits.count('/api/audit')==i
                page.click('#audit');page.wait_for_selector('#versions',state='visible');assert hits.count('/api/audit')==i+1
                assert '[0, ' not in page.locator('#byteReceipt').inner_text() and 'bytes' in page.locator('#byteReceipt').inner_text()
                assert 'Open audit' not in page.locator('#blocks').inner_text()
                if case=='relocated':
                    assert 'match both snapshots' in page.locator('#result').inner_text() and total==2
                    if screenshot:page.screenshot(path=str(screenshot))
                elif case=='changed':
                    assert total==3 and overlap==2 and '74 bytes' in page.locator('#spanIds').inner_text()
                else:
                    page.click('#stale');assert 'Block #75' in page.locator('#detail h3').inner_text()
                    assert '596' in page.locator('#detail table tr').nth(1).inner_text() and '3 of 101' in page.locator('#counts').inner_text()
                page.locator('#versions summary').click();assert 'Before' in page.locator('#digests').inner_text()
                observation[case]=dict(blocks=total,overlapping=overlap,decision=page.locator('#result').inner_text())
            ctx.close();b.close()
    finally:server.terminate();server.wait(timeout=8)
    assert not errors and not remote
    return dict(cases=observation,packet_requests=hits.count('/api/packet'),explicit_audits=hits.count('/api/audit'),page_errors=errors,remote_requests=remote)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path);p.add_argument('--screenshot',type=Path);args=p.parse_args()
    result=run(args.screenshot);print(json.dumps(result))
    if args.out:args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n',encoding='utf8')
