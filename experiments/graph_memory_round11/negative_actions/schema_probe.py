import gzip,json,re,collections
from pathlib import Path
d=Path(__file__).resolve().parents[2]
for group,src,term in (('kimi','graph_memory_round5/action_transfer/source_0.gz','graph_memory_round5/action_transfer/terminal_0.gz'),('claude','graph_memory_round6/version/external/source.gz','graph_memory_round6/version/external/terminal.gz')):
 with gzip.open(d/src,'rt',encoding='utf8') as source, gzip.open(d/term,'rt',encoding='utf8') as log:
  types=collections.Counter();zero=[]
  for s,t in zip(source,log):
   q=json.loads(s);i,terms=json.loads(t)
   if q['official_repo'] in ('django/django',):continue
   if not types:print(group,'keys',q.keys(),'event example',str(q['events'][0])[:650], 'other',[(k,str(v)[:180]) for k,v in q.items() if k not in ('events','problem_statement')][:9])
   for e,ex in zip(q['events'],terms):
    types[e[0]]+=1
    if ex:
     c=ex['command'];lines=[line for _,_,seg in ex['pieces'] for line in seg]
     if re.match(r'\s*(grep|rg|find|ls|cat)\b',c) and (len(lines)<3 or (lines and 'code' in lines[-1].lower())) and len(zero)<13:zero.append((c[:135],lines[:2],ex['raw_length'],ex['shown_length']))
    elif e[0]=='view' and len(zero)<13 and len(str(e))<300:zero.append((str(e)[:235],))
  print('types',types)
  for ex in zero:print(str(ex)[:330])
