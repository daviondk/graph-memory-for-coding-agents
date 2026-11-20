from pathlib import Path
import re, json, zipfile, collections, html, unicodedata
from markdown_it import MarkdownIt
from bs4 import BeautifulSoup
w=Path(__file__).resolve().parent
out=w.parent/'outputs'
out.mkdir(exist_ok=True)
def readjson(p):return json.loads(p.read_text('utf-8-sig'))
def dump(o):return json.dumps(o,ensure_ascii=False,indent=2)
E=html.escape
rows=[]
links=readjson(w/'external.json')
pubstatus={'2509.25140':'ICLR 2026 (по версии авторов)','2410.10813':'ICLR 2025 (по версии авторов)','2310.06770':'ICLR 2024 (по версии авторов)','2508.21433':'DL4Code, NeurIPS 2025 workshop','2610.27377':'CLEA, NeurIPS 2026 workshop (принята, по версии авторов)','2611.14320':'Препринт, submitted to ACL Rolling Review','2608.08239':'COLM 2026 (по версии авторов)','2303.11366':'NeurIPS 2023'}
inspected=set('2611.14320 2610.04838 2610.27377 2611.17316 2610.27524 2609.23570 2610.10263 2610.41433'.split())
bib_entries=[]
for line in (w/'registry.txt').read_text('utf-8').splitlines():
    i,short,group,note=line.split('|',3)
    a=w/'sources'/(i+'.json'); ar=readjson(a) if a.exists() else {}
    p=w/'pub'/(i+'.json'); pub=readjson(p) if p.exists() else {}
    src=pub or ar
    title=src['title']
    title=title.replace('Agents?Benchmarking','Agents? Benchmarking').replace('Agents:Mechanisms','Agents: Mechanisms')
    yr=(pub.get('date') or [ar.get('date','')[:4]])[0]
    venue=pub.get('venue') or pubstatus.get(i,'версия arXiv')
    id_url=src['url']
    authors=src['authors']
    key='ref'+(i.replace('.','') if ar else i)
    record={'id':i,'short_name':short,'topic':group,'title':title,'authors':authors,
            'year_of_cited_version':yr,'arxiv_initial_date':ar.get('date','').replace('/','-') or None,
            'cited_version_or_venue':venue,'url':id_url,'arxiv_url':ar.get('url'),'publisher_doi':pub.get('doi'),
            'arxiv_version':(re.findall(r'\[(v\d+)\]',ar.get('versions','')) or [None])[-1],
            'checked':'2026-11-16','assessment_ru':note,'source_depth_ru':'выборочная сверка методов или результатов по полному тексту' if i in inspected else ('запись издателя и аннотация' if pub else 'карточка arXiv и аннотация авторов'),
            'bibtex_key':key}
    rows.append(record)
    links[i]=[short,id_url]
    if pub.get('bib'):
        raw=pub['bib']
        # Keep the bibliographic part of publisher-provided BibTeX, omit the abstract.
        raw=re.sub(r',?\s*abstract\s*=\s*".*?"\s*(?=\n\})','',raw,flags=re.I|re.S)
        raw=re.sub(r'(@\w+\{)[^,]+',lambda m:m[1]+key,raw,count=1)
        if ar and 'eprint =' not in raw:
            raw=raw.rstrip()[:-1].rstrip().rstrip(',')+',\n    eprint = {'+i+'},\n    archivePrefix = {arXiv}\n}'
        bib_entries.append(raw.strip())
    else:
        typ={'journal-article':'article','proceedings-article':'inproceedings'}.get(pub.get('type'),'misc')
        def esc(x):
            return str(x).replace('&',r'\&').replace('%',r'\%').replace('_',r'\_').replace('#',r'\#')
        fields={'title':'{'+esc(title)+'}','author':' and '.join(esc(x) for x in authors),'year':str(yr)}
        if pub: fields['journal' if typ=='article' else 'booktitle']=esc(venue)
        if ar:
            fields.update(eprint=i,archivePrefix='arXiv')
        if pub.get('doi'):fields['doi']=pub['doi']
        if not pub and i in pubstatus: fields['note']=ar.get('status','')[:0] or {'2611.14320':'Submitted to ACL Rolling Review','2610.27377':'Accepted at CLEA workshop at NeurIPS 2026','2508.21433':'DL4Code workshop at NeurIPS 2025','2608.08239':'Accepted at COLM 2026','2310.06770':'ICLR 2024','2303.11366':'NeurIPS 2023','2509.25140':'ICLR 2026','2410.10813':'ICLR 2025'}[i]
        fields['url']=id_url
        bib_entries.append('@'+typ+'{'+key+',\n'+',\n'.join('  '+n+' = {'+v+'}' for n,v in fields.items())+'\n}')
bib='\n\n'.join(bib_entries)+'\n'
(out/'agent-memory.bib').write_text(bib,encoding='utf-8')
def cite(m):
    key=m[1]; label,u=links[key];return '<a class="cite" href="'+E(u,quote=True)+'">'+E(label)+'</a>'
md=(w/'report_a.md').read_text('utf-8')+'\n\n'+(w/'report_b.md').read_text('utf-8')
md=re.sub(r'\[\[([^\]]+)\]\]',cite,md)
body=MarkdownIt('commonmark',{'html':True}).enable('table').render(md)
s=BeautifulSoup(body,'html.parser')
title=s.h1.extract().get_text()
lead=s.p.extract().get_text()
toc=[]
for q,h in enumerate(s.find_all('h2'),1):
    h['id']='sec'+str(q); toc.append((h['id'],h.get_text().split('. ',1)[-1]))
for t in s.find_all('table'):
    div=s.new_tag('div',attrs={'class':'tablebox'});t.wrap(div)
for tag in s.find_all('a'):tag['rel']='noopener'
nav=''.join('<a href="#'+i+'">'+E(t)+'</a>' for i,t in toc+[('sources','Аннотированная библиография')])
cards=[]
for j in sorted(rows,key=lambda j:(j['topic'],j['short_name'].casefold())):
    who=j['authors'][0].split(',')[0]+(' и др.' if len(j['authors'])>1 else '')
    keywords=' '.join([j['short_name'],j['id'],j['publisher_doi'] or '',*j['authors']])
    cards.append('<article class="ref" data-group="'+E(j['topic'])+'" data-keywords="'+E(keywords,quote=True)+'"><small>'+E(j['short_name'])+' · '+E(j['topic'])+' · '+E(who)+' · '+str(j['year_of_cited_version'])+'</small><h4><a href="'+E(j['url'])+'">'+E(j['title'])+'</a></h4><p>'+E(j['assessment_ru'])+'</p><footer>'+E(j['cited_version_or_venue'])+' · '+E(j['source_depth_ru'])+'</footer></article>')
opts=''.join('<option>'+E(x)+'</option>' for x in sorted(set(j['topic'] for j in rows)))
page=(w/'layout.html').read_text('utf-8').replace('@@TITLE@@',E(title)).replace('@@LEAD@@',E(lead)).replace('@@NAV@@',nav).replace('@@BODY@@',str(s)).replace('@@CARDS@@','\n'.join(cards)).replace('@@GROUPS@@',opts).replace('@@N@@',str(len(rows)))
(out/'agent-memory-review.html').write_text(page,encoding='utf-8')
queries=sum([readjson(w/name) for name in ['web_queries.json','web_queries_extra.json','web_queries_recent.json']],[])
db=readjson(w/'dbsearch.json')
audit=readjson(w/'audit_v2.json')
counts={'catalog_records':len(rows),'bibliographic_database_hits':{x:sum(len(s['records']) for s in db if s['db']==x) for x in set(s['db'] for s in db)},'distinct_exact_titles_database_only':len(set(r['title'] for d in db for r in d['records'])),'web_search_strings_logged':sum(len(q['query']) if isinstance(q['query'],list) else 1 for q in queries)}
meta={'run_date_local':'2026-11-16','timezone':'Europe/Moscow','review_type':'targeted scoping review; single reviewer; no meta-analysis','counts':counts,'limitations':['arXiv query result caps 100, OpenAlex first 50 per query. Supplemented by targeted primary-source search.','Journal/venue fields only when identified. Crossref rate limits affected publisher matching; arXiv entries may have additional published versions.','A search hit is not an included source. Repeated database records are retained in the discovery log.','For the trace audit, parse rules were revised after the strict parser produced zero results. Records come from public historical trajectories, not new agent runs.']}
with zipfile.ZipFile(out/'agent-memory-research.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
    def put(n,txt):z.writestr(n,txt.encode('utf-8'))
    put('README.txt',(w/'package-readme.txt').read_text('utf-8'));put('manifest.json',dump(meta))
    put('sources/evidence.jsonl','\n'.join(json.dumps(j,ensure_ascii=False) for j in rows)+'\n')
    put('sources/technical-and-project-sources.json',dump(readjson(w/'external.json')))
    put('sources/agent-memory.bib',bib)
    put('search/database-results.json',dump(db));put('search/web-searches.json',dump(queries))
    put('audit/audit.py',(w/'audit.py').read_text('utf-8'));put('audit/trace-results.json',dump(audit));put('audit/initial-strict-counts.json',dump(readjson(w/'audit.json')['counts']))
    put('audit/anchor_sensitivity.py',(w/'anchor_sensitivity.py').read_text('utf-8'))
    put('audit/anchor-sensitivity.json',dump(readjson(w/'anchors.json')))
    put('protocol/codex-exec-help.txt',(w/'codex-exec-help.txt').read_text('utf-8-sig'));put('protocol/experiment.txt',(w/'report_b.md').read_text('utf-8').split('## 6. ',1)[1].split('## 7. ',1)[0])
print(dump(counts))

