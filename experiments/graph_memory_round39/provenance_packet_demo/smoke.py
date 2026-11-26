"""Exercise real HTTP queries and optionally drive installed Chromium through Playwright."""
import argparse
from contextlib import contextmanager
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import urlencode,urlsplit
from urllib.request import urlopen
from reader import D,Reader,Evaluator

@contextmanager
def running():
    p=subprocess.Popen([sys.executable,'-B','-u',str(D/'serve.py'),'--port','0'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        url=p.stdout.readline().strip()
        if not url.startswith('http://127.0.0.1:'):raise RuntimeError('server failed to start')
        yield url
    finally:p.terminate();p.wait(timeout=10)

def exercise(browser=False,screenshot=None):
    obs=json.loads(gzip.decompress((D/'observations.json.gz').read_bytes()));case=next(q for q,v in sorted(obs.items()) if v['exclude']['added'] or v['exclude']['removed']);source=obs[case]['exclude']['exclude']
    requests=0;reader=Reader();grader=Evaluator();out={}
    with running() as url:
        def fetch(endpoint):
            nonlocal requests
            requests+=1
            with urlopen(url+endpoint,timeout=30) as resp:return json.load(resp)
        queries=fetch('/api/queries')['queries'];assert len(queries)==40
        for scenario,opts in [('main',(2048,None)),('small',(1024,None)),('large',(3072,None)),('exclude',(2048,source)),('restore',(2048,None))]:
            budget,exc=opts;parameters=dict(q=case,budget=budget)
            if exc:parameters['exclude']=exc
            qs='?'+urlencode(parameters);api=fetch('/api/packet'+qs);packet=reader.choose(case,budget,exc)
            assert api['packet']==packet and [v['id'] for v in api['items']]==packet['ids'] and not {'full_support','coverage','gold'}&api.keys()
            assert api['items']==reader.explain(packet) and api['sources']==reader.sources(case)
            ev=fetch('/api/evaluate'+qs);assert ev==grader.evaluate(reader,packet)
            out[scenario]=dict(ids=packet['ids'],tokens=packet['tokens'],**ev)
        assert out['restore']==out['main'] and out['main']['ids']!=out['exclude']['ids']
        for path in ('/api/packet?q=unknown&budget=2048','/api/packet?q=q01&budget=2049','/api/packet?q=q01&budget=2048&exclude=unknown'):
            try:fetch(path)
            except HTTPError as e:assert e.code==400
            else:raise AssertionError(path)
        report=dict(query=case,http_requests=requests,invalid_rejected=3,observed=out)
        if browser:
            from playwright.sync_api import sync_playwright
            exe=os.environ.get('BROWSER_EXE') or next(str(p) for p in [Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')] if p.exists())
            with sync_playwright() as pw:
                chrome=pw.chromium.launch(executable_path=exe,headless=True,args=['--disable-background-networking']);ctx=chrome.new_context(viewport={'width':1340,'height':970});page=ctx.new_page();remote=[];errors=[];visits=[]
                page.on('pageerror',lambda exc:errors.append(str(exc)))
                def route(req):
                    parsed=urlsplit(req.request.url)
                    if parsed.hostname!='127.0.0.1':remote.append(req.request.url);req.abort();return
                    visits.append(parsed.path);req.continue_()
                ctx.route('**/*',route);page.goto(url)
                def wait(q,b,e=''):page.wait_for_function('key=>document.documentElement.dataset.ready===key',arg=f'{q}|{b}|{e}')
                wait(queries[0],2048);page.select_option('#q',case);wait(case,2048);page.select_option('#budget','1024');wait(case,1024);page.select_option('#budget','2048');wait(case,2048);page.select_option('#source',source);wait(case,2048,source)
                assert '/api/evaluate' not in visits and page.locator('#score').inner_text()==''
                assert [int(t[1:]) for t in page.locator('#rows button').all_inner_texts()]==out['exclude']['ids']
                page.locator('#rows button').last.click();assert page.locator('.graphrow').count()>0
                assert '—'!=page.locator('#delta div').first.inner_text().split(': ',1)[-1]
                page.click('#grade');page.wait_for_function("document.getElementById('score').textContent.includes('символов')");assert visits.count('/api/evaluate')==1
                if screenshot:page.screenshot(path=str(screenshot),full_page=True)
                page.click('#reset');wait(case,2048);assert page.locator('#score').inner_text()==''
                page.select_option('#q',queries[-1]);wait(queries[-1],2048)
                ctx.close();chrome.close();assert not errors and not remote
                report['browser']=dict(browser='Chromium',query_changes=2,explicit_grade=1,source_changes=2,external_requests=len(remote),page_errors=errors)
        return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--browser',action='store_true');p.add_argument('--screenshot',type=Path);p.add_argument('--out',type=Path);a=p.parse_args();v=exercise(a.browser,a.screenshot)
    if a.out:
        with a.out.open('x',encoding='utf8') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n')
    print(v.get('browser',{}),v['http_requests'],v['query'])
