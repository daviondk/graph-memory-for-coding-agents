"""Match all score tables in the deliverable back to result JSON independently of prose."""
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

here=Path(__file__).resolve().parent
root=here.parent
def load(f):return json.loads((root/f).read_text(encoding='utf8'))
def pct(v):return ('%.2f%%'%(v*100)).replace('.',',')
def clean(s):return s.replace('\u00a0','').replace(' ','')
def scan(name):
    rows=[]
    for line in (here/'pages'/(name+'.md')).read_text(encoding='utf8').splitlines():
        if line.startswith('|'):
            rows.append([v.strip() for v in line.strip('|').split('|')])
    return rows[1:]
def norm(r):return [[clean(y) for y in x] for x in r]
checks=[]
def eq(name,actual,expected):
    assert norm(actual)==norm(expected),(name,actual,expected)
    checks.append(name)

for page_id,group,arms in [
    ('06','run',['recency','lexical','raw_smoothed','unit_smoothed','online_mix']),
    ('07','transfer_run',['lexical','raw_smoothed','mass_matched_raw','unit_smoothed','online_mix']),
    ('07b','exposure_run',['lexical','unit_smoothed','exposure_matched'])]:
    d=load('git_prediction/'+group+'/summary.json')['evaluation']['macro']
    expected=[[pct(d[a]['r5'])]+([pct(d[a]['h1'])] if page_id!='07b' else []) for a in arms]
    eq(page_id,[r[1:] for r in scan(page_id)],expected)
d=load('git_reader/results.json')
expected=[[f'{d["arms"][a]["hit"]}/24',str(d['arms'][a]['input_tokens'])] for a in ['masked','true','shuffled']]
expected += [[f'{d["deterministic"][a]}/24','—'] for a in ['graph','lexical']]
eq('08',[r[1:] for r in scan('08')],expected)
d=load('official_retrieval/scores.json')
expected=[]
for setup in ['fusion_lite','recall_lite','online_lite']:
    m=d[setup]['methods']
    expected.append([str(m[a]['Hit@1']) for a in ['base','direct','graph']]+[f'{m["base"]["Hit@5"]}/{m["graph"]["Hit@5"]}'])
eq('09',[r[1:] for r in scan('09')],expected)
d=load('proofs/results.json')
methods=['one','short3','diverse','historical']
expected=[[f'{d[g]["arms"][a]["fast"]["total"]}/{d[g]["queries"]}' for g in ['A','B']] for a in methods]
eq('11',[r[1:] for r in scan('11')],expected)
d=load('proofs/lazy/summary.json')['groups']['all']
expected=[]
for a in ['direct']+methods:
    v=[d[a][i]['blob_objects'] for i in ['write','read']]
    expected.append([str(i) for i in v+[sum(v)]])
eq('12',[r[1:]for r in scan('12')],expected)
d=load('proofs/transfer/results.json')['totals']
eq('13',[r[1:] for r in scan('13')],[[f'{d["fast"][a]}/{d["n"]}'] for a in methods])
d=load('proofs/free/results.json')['all']
eq('14',[r[1:] for r in scan('14')],[[str(d[a]['read_blob']),f'{d[a]["correct"]}/{d[a]["n"]}',str(d[a]['stored_bytes'])] for a in ['direct','blind','one','short','free','edge']])
docpath=here/'final'/'graph-memory-research-round1.docx'
with zipfile.ZipFile(docpath) as z:
    xml=ET.fromstring(z.read('word/document.xml'))
    w='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    doc_tables=[]
    for table in xml.iter(w+'tbl'):
        doc_tables.append([[clean(''.join(t.text or '' for t in c.iter(w+'t'))) for c in row.findall(w+'tc')] for row in table.findall(w+'tr')][1:])
    for p in sorted((here/'pages').glob('*.md')):
        rows=scan(p.stem)
        if rows:
            assert norm(rows) in doc_tables, 'visually authored table differs from actual Word: '+p.name
save={'raw_score_tables':checks,'word_tables':len(doc_tables),'result':'passed'}
(here/'final'/'source-audit.json').write_text(json.dumps(save,indent=2),encoding='utf8')
print(save)

