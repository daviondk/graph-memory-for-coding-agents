from collect import root, fetch, urlencode
from pathlib import Path
from xml.etree import ElementTree as ET
import json, time
end=' AND submittedDate:[202001010000 TO 202611162359]'
aq=['(ti:"coding agents" OR ti:"code agents" OR ti:"software engineering agents") AND (ti:memory OR abs:"experience memory" OR ti:"sub-agents")','(ti:"repository" OR ti:"code repair" OR ti:"coding tasks") AND (ti:memory OR ti:"context learning")','(ti:"memory" AND (abs:"software engineering" OR abs:"coding agents")) AND submittedDate:[202610010000 TO 202611162359]','(ti:"sub-agents" OR ti:"subagents") AND (abs:codex OR abs:"coding agents")']
oq=['"coding agents" memory','"coding agents" experience trajectory','"software engineering" "agent memory"','"coding agents" "sub-agents"']
log=[]
for q in aq:
    u='https://export.arxiv.org/api/query?'+urlencode({'search_query':q+end,'start':0,'max_results':100,'sortBy':'relevance'})
    row={'db':'arXiv API','query':q+end,'url':u}
    try:
        data=ET.fromstring(fetch(u))
        row['total']=data.findtext('{*}totalResults')
        row['records']=[{'title':' '.join(x.findtext('{*}title').split()),'url':x.findtext('{*}id'),'date':x.findtext('{*}published')} for x in data.findall('{*}entry')]
    except Exception as e: row['error']=str(e)
    log.append(row)
    time.sleep(3)
for q in oq:
    u='https://api.openalex.org/works?'+urlencode({'search':q,'filter':'from_publication_date:2020-01-01,to_publication_date:2026-11-16','per_page':50,'select':'id,doi,display_name,publication_date'})
    row={'db':'OpenAlex','query':q,'url':u}
    try:
        data=json.loads(fetch(u))
        row['total']=data['meta']['count']
        row['records']=[{'title':x['display_name'],'url':x['doi'] or x['id'],'date':x['publication_date']} for x in data['results']]
    except Exception as e: row['error']=str(e)
    log.append(row)
(root/'dbsearch.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
for r in log: print(r['db'],r.get('total'),len(r.get('records',[])),r.get('error',''))

