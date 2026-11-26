"""Run integration tests against the packaged databases or the signed research fixtures."""
import argparse
from contextlib import closing
from http.server import BaseHTTPRequestHandler,HTTPServer
import json
import os
from pathlib import Path
from threading import Thread
import urllib.error
from urllib.parse import urlencode
from urllib.request import urlopen
import weights

D=Path(__file__).resolve().parent
W=D.parents[1]
DEFAULT_INDEX=W/'graph_memory_round46/trust_view/view.sqlite'
DEFAULT_READER=W/'graph_memory_round45/paper_revision/apps/trace/runtime/reader.sqlite'

def verify_data(index_path,reader_path):
    checked=0
    with closing(weights.connect(index_path)) as ix,closing(weights.connect(reader_path)) as rd:
        qs=[q for q, in ix.execute('select distinct q from edge order by q')]
        assert len(qs)==40
        total_sources=0
        for q in qs:
            choices=weights.source_choices(ix,rd,q);total_sources+=len(choices)
            s=choices[0]['id'];state=weights.lookup(ix,rd,q,s,0)
            probes={weights.LOW,0,weights.HIGH}
            for r in state['intervals']:
                probes.update([r['lo'],r['hi']])
            for delta in sorted(probes):
                out=weights.lookup(ix,rd,q,s,delta,True)
                assert out['lo']<=delta<=out['hi'] and out['verification']['equal']
                assert out['verification']['tokens']==out['after']['tokens']<=2048
                assert out['unchanged']==(out['before']['members']==out['after']['members'])
                checked+=1
        assert total_sources==2528
    return checked

def browser_tests(index_path,reader_path,out):
    from playwright.sync_api import sync_playwright
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if not weights.handle_weights(self,index_path=index_path,reader_path=reader_path):
                self.send_error(404)
        def log_message(self,*args):pass
    report={}
    with HTTPServer(('127.0.0.1',0),Handler) as server:
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        root=f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as p:
                host=os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)')
                edge=Path(host)/'Microsoft/Edge/Application/msedge.exe'
                opts={'executable_path':str(edge)} if edge.exists() else {}
                browser=p.chromium.launch(headless=True,**opts)
                for name,width,height in [('desktop',1180,820),('mobile',390,844)]:
                    page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
                    errors=[];page.on('pageerror',lambda exc:errors.append(str(exc)))
                    page.goto(root+'/weights')
                    page.wait_for_function("document.documentElement.dataset.ready?.endsWith('|6307133')")
                    assert page.locator('#status').inner_text().startswith('Packet changed')
                    assert page.locator('#before .minus').count() and page.locator('#after .plus').count()
                    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
                    page.locator('#verify').click()
                    page.wait_for_function("document.querySelector('#proof').textContent.startsWith('Exact match')")
                    if out:page.screenshot(path=out/(name+'.png'),full_page=True)
                    q,s,d=page.locator('html').get_attribute('data-ready').split('|')
                    assert int(d)==6307133
                    direct=json.load(urlopen(root+'/api/weights/verify?'+urlencode(dict(q=q,s=s,delta=d))))
                    assert direct['verification']['equal']
                    page.locator('#prev').click()
                    page.wait_for_function("document.documentElement.dataset.ready?.endsWith('|6307132')")
                    assert 'Original packet retained' in page.locator('#status').inner_text()
                    page.locator('#next').click();page.wait_for_function("document.documentElement.dataset.ready?.endsWith('|6307133')")
                    page.locator('#zero').click();page.wait_for_function("document.documentElement.dataset.ready?.endsWith('|0')")
                    page.locator('#amount').fill(str(weights.HIGH));page.locator('#amount').press('Enter')
                    page.wait_for_function("document.documentElement.dataset.ready?.endsWith('|1073741824')")
                    assert page.locator('#next').is_disabled()
                    page.locator('#q').select_option('q40')
                    page.wait_for_function("document.documentElement.dataset.ready?.startsWith('q40|')")
                    assert not errors
                    report[name]=dict(width=width,height=height,original=direct['before']['members'],changed=direct['after']['members'],
                        source=s,first_changed=int(d),exact=True,horizontal_overflow=False)
                    page.close()
                browser.close()
            for endpoint in ['/api/weights/packet?q=q01&s=bad&delta=0',
                    '/api/weights/packet?q=q01&s=bad&delta=1073741825','/api/weights/packet','/api/weights/sources?q=bogus']:
                try:urlopen(root+endpoint)
                except urllib.error.HTTPError as e:assert e.code==400
                else:raise AssertionError('Invalid request accepted')
        finally:server.shutdown();thread.join()
    return report

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--index',type=Path,default=DEFAULT_INDEX)
    cli.add_argument('--reader',type=Path,default=DEFAULT_READER);cli.add_argument('--screens',type=Path)
    cli.add_argument('--browser',action='store_true');args=cli.parse_args()
    n=verify_data(args.index,args.reader)
    if args.screens:args.screens.mkdir(exist_ok=True,parents=True)
    report=browser_tests(args.index,args.reader,args.screens) if args.browser else {}
    print(json.dumps(dict(probes=n,browser=report),sort_keys=True))
