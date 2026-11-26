"""Test the English visitor scenario using an installed Chromium and Playwright."""
import argparse,json,os,subprocess,sys
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

D=Path(__file__).resolve().parent
if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--screenshot',type=Path);cli.add_argument('--out',type=Path);opts=cli.parse_args()
    p=subprocess.Popen([sys.executable,'-B','-u',str(D/'launcher.py'),'--port','0'],stdout=subprocess.PIPE,text=True); url=p.stdout.readline().strip(); assert url.startswith('http://127.0.0.1:')
    try:
        with sync_playwright() as pw:
            exe=os.environ.get('BROWSER_EXE') or next(str(p) for p in (Path('C:/Program Files/Google/Chrome/Application/chrome.exe'), Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')) if p.exists())
            browser=pw.chromium.launch(executable_path=exe,headless=True,args=['--disable-background-networking']);ctx=browser.new_context(viewport={'width':1040,'height':810},device_scale_factor=1.5);page=ctx.new_page();requests=[];errors=[];remote=[]
            def route(r):
                parsed=urlsplit(r.request.url)
                if parsed.hostname=='127.0.0.1':requests.append(parsed.path);r.continue_()
                else:remote.append(parsed.hostname);r.abort()
            ctx.route('**/*',route);page.on('pageerror',lambda e:errors.append(str(e)));page.goto(url);page.wait_for_function("document.documentElement.dataset.ready==='q02|2048||certificate'")
            page.click('#clean');page.wait_for_function("document.getElementById('action').textContent==='Reuse cached packet'");assert '/api/audit' not in requests
            page.click('#grade');page.wait_for_function("document.getElementById('result').textContent.includes('Matches full')")
            page.click('#hit');page.wait_for_function("document.getElementById('action').textContent==='Recompute packet'");assert page.locator('#change').inner_text().startswith('Added #19')
            page.click('#grade');page.wait_for_function("document.getElementById('result').textContent.includes('Matches full')");
            if opts.screenshot:page.screenshot(path=str(opts.screenshot),clip={'x':0,'y':0,'width':1040,'height':550})
            page.click('#boundary');page.wait_for_function("document.getElementById('guards').textContent.includes('Boundary dependency: yes')");assert page.locator('#proof').inner_text().startswith('Removing the prefix boundary')
            page.select_option('#mode','full');page.wait_for_function("document.documentElement.dataset.ready.endsWith('|full')");page.click('#grade');page.wait_for_function("document.getElementById('result').textContent.includes('Matches full')");page.click('#reset');page.wait_for_function("document.getElementById('action').textContent==='Original packet'");page.select_option('#b','1024');page.wait_for_function("document.documentElement.dataset.ready.includes('|1024|')");browser.close()
            assert not remote and not errors and requests.count('/api/audit')==3
            if opts.out:opts.out.write_text(json.dumps(dict(audits=3,full_recomputation_checked=True,packet_swap=[11,19],boundary_case='q07',external_requests=remote,page_errors=errors),sort_keys=True,indent=2)+'\n',encoding='utf8')
    finally:p.terminate();p.wait(timeout=8)
