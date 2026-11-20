from collect import root, raw, fetch
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import requests, re, json, datetime, unicodedata
from bs4 import BeautifulSoup
def norm(t):
    return ''.join(c for c in unicodedata.normalize('NFKD',t.lower()) if c.isalnum())
def pub_date(r):
    return r.get('published',{}).get('date-parts',[[9999]])[0]
def cross(r):
    names=[]
    for person in r.get('author',[]):
        if person.get('family'): names.append(', '.join(filter(None,[person['family'],person.get('given')])))
    return {'title':BeautifulSoup(r['title'][0],'html.parser').get_text(),'authors':names,'doi':r['DOI'],'venue':(r.get('container-title') or [''])[0],
        'type':r['type'],'date':pub_date(r),'url':'https://doi.org/'+r['DOI']}
def find(item):
    id,short,group,note=item
    dir=root/'pub'
    dir.mkdir(exist_ok=True)
    p=dir/(id+'.json')
    if p.exists():return
    try:
        pinned={'hindsight':'10.18653/v1/2026.acl-demo.27','prism':'10.18653/v1/2026.findings-emnlp.1301','2607.02606':'10.18653/v1/2026.emnlp-main.371','2608.21867':'10.18653/v1/2026.emnlp-main.423','2604.14004':'10.18653/v1/2026.emnlp-main.2666','2511.03506':'10.18653/v1/2026.emnlp-main.220','2607.27250':'10.18653/v1/2026.realm-1.5'}
        if id in pinned:
            base='https://aclanthology.org/'+pinned[id].split('v1/')[1]+'/'
            s=BeautifulSoup(fetch(base),'html.parser')
            def meta(k):return [v.get('content') for v in s.select(f'meta[name="{k}"]')]
            title=meta('citation_title')[0]; names=meta('citation_author')
            reg={'title':title,'authors':names,'url':base,'doi':pinned[id],'type':'proceedings-article',
                 'venue':meta('citation_conference_title')[0] if meta('citation_conference_title') else s.select_one('span.venue') and s.select_one('span.venue').get_text(strip=True),
                 'date':[int(x) for x in meta('citation_publication_date')[0].split('/') if x.isdigit()] if meta('citation_publication_date') else [2026],
                 'bib':fetch(base.rstrip('/')+'.bib').decode('utf-8')}
            if not reg['venue']:
                match=re.search(r'booktitle\s*=\s*["{](.*?)[}"],?\s*\n',reg['bib'])
                reg['venue']=match[1] if match else 'ACL Anthology'
        else:
            j=json.loads((raw/(id+'.json')).read_text('utf-8'))
            res=requests.get('https://api.crossref.org/works',params={'query.bibliographic':j['title'],'rows':3},timeout=16)
            res.raise_for_status()
            rs=[cross(d) for d in res.json()['message']['items'] if d.get('title') and d.get('type') in ('journal-article','proceedings-article') and pub_date(d)<=[2026,11,16]]
            reg=next((d for d in rs if norm(d['title'])==norm(j['title']) and d['authors'] and norm(d['authors'][0].split(',')[0])==norm(j['authors'][0].split(',')[0])),None)
        if reg: p.write_text(json.dumps(reg,ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception as e: print(id,str(e)[:170])
rows=[ln.split('|',3) for ln in (root/'registry.txt').read_text('utf-8').splitlines() if ln]
with ThreadPoolExecutor(max_workers=5) as ex:list(ex.map(find,rows))
print('Confirmed journal or proceedings:',len(list((root/'pub').glob('*.json'))))

