from pathlib import Path
from zipfile import ZipFile
import json,re
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parent.parent
out=root/'outputs'
doc=out/'agent-memory-review.html'
s=BeautifulSoup(doc.read_text('utf-8'),'html.parser')
assert not re.search(r'@@[A-Z]+@@|\[\[[\w.-]+\]\]',s.get_text())
assert len(s.select('.ref'))==74
assert len(s.select('main table'))==5
for t in s.select('main table'):
    widths={len(tr.select('th,td')) for tr in t.select('tr')}
    assert len(widths)==1,widths
assert all(s.select_one(a['href']) for a in s.select('nav a[href^="#"]'))
with ZipFile(out/'agent-memory-research.zip') as z:
    assert not z.testzip()
    rows=[json.loads(i) for i in z.read('sources/evidence.jsonl').decode().splitlines()]
    keys=[i['bibtex_key'] for i in rows]
    bib=z.read('sources/agent-memory.bib').decode()
    assert list(dict.fromkeys(keys))==keys
    assert set(re.findall(r'^@\w+\{([^,]+),',bib,re.M))==set(keys)
    assert bib.count('{')==bib.count('}')
    a=json.loads(z.read('audit/trace-results.json'));assert len(a['traces'])==64
    assert sum(a['counts']['outcomes'].values())==a['counts']['events']==231
    assert not any('reasoning_content' in str(t) for t in a['traces'])
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1350,'height':880},device_scale_factor=1)
    err=[]
    page.on('pageerror',lambda e: err.append(str(e)))
    page.goto(doc.as_uri()); assert page.locator('article.ref:visible').count()==74
    page.screenshot(path=str(root/'work'/'review-desktop.png'))
    page.locator('#query').fill('WikiTrace')
    assert page.locator('article.ref:visible').count()==1
    page.locator('#query').fill('');page.locator('#topic').select_option(label='Субагенты');assert page.locator('article.ref:visible').count()==3
    page.set_viewport_size({'width':390,'height':800});page.locator('#top').scroll_into_view_if_needed();page.evaluate('window.scrollTo(0,0)')
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    page.screenshot(path=str(root/'work'/'review-mobile.png'))
    assert not err,err
    print('Verified bibliography, data archive, links within document, tables, and desktop/mobile navigation.')
    browser.close()

