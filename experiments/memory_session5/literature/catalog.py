"""Metadata-only, bounded scholarly queries. Search indexes are discovery aids only."""
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote
import json, requests
ROOT=Path(__file__).resolve().parent
IDS='2609.20050 2507.03724 2505.22101 2608.00808 2601.16746 2607.18213 2611.14009 2610.15093 2610.34673 2504.21798 2611.12068 2611.14320 2508.21433 2610.27377 2611.03930'.split()
class Meta(HTMLParser):
    def __init__(self):
        super().__init__();self.meta={}
    def handle_starttag(self,tag,atts):
        x=dict(atts); k=x.get('name','')
        if tag=='meta' and k.startswith('citation_') and 'content' in x:
            self.meta.setdefault(k,[]).append(x['content'])
def retrieve(i):
    url='https://arxiv.org/abs/'+i
    res=requests.get(url,timeout=30);p=Meta();p.feed(res.text)
    return {'id':i,'source_url':url,'status':res.status_code,'meta':p.meta}
def search(args):
    system,q=args
    try:
        if system=='OpenAlex':
            res=requests.get('https://api.openalex.org/works',params={'search':q,'per-page':5,'select':'id,doi,display_name,publication_year'},timeout=20)
            rows=res.json().get('results',[])
        else:
            res=requests.get('https://api.semanticscholar.org/graph/v1/paper/search',params={'query':q,'limit':5,'fields':'title,year,externalIds,url'},timeout=20)
            rows=res.json().get('data',[])
        return {'database':system,'query':q,'status':res.status_code,'hits':rows}
    except Exception as e:return {'database':system,'query':q,'error':type(e).__name__}
def main():
    with ThreadPoolExecutor(5) as t: papers=list(t.map(retrieve,IDS))
    queries=[(v,q) for v in ('OpenAlex','Semantic Scholar') for q in ('coding agents minimal sufficient evidence working memory','coding agent observation masking history compression')]
    with ThreadPoolExecutor(3) as t: searches=list(t.map(search,queries))
    for key,val in [('metadata',papers),('database_search',searches)]:
        (ROOT/(key+'.json')).write_text(json.dumps(val,ensure_ascii=False,indent=1),encoding='utf8')
    print([(p['id'],p['meta'].get('citation_title',[None])[0]) for p in papers])
    print([(s.get('database'),s.get('status'),len(s.get('hits',[]))) for s in searches])
if __name__=='__main__':main()


