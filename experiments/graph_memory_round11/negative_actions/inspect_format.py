import json,collections,gzip,urllib.request
from pathlib import Path
d=Path(__file__).resolve().parents[2]
for i,rc in enumerate([json.load(open(d/'graph_memory_round6/version/external/roster_lock.json'))['manifest'][0],json.load(open(d/'graph_memory_round5/action_transfer/receipts.json'))[1]]):
 raw=urllib.request.urlopen(rc['url'],timeout=25).read();s=json.loads(raw);print(str(s.keys())[:400],list(s['trajectory'][0]))
 for step in s['trajectory'][:26]:
  if not step.get('observation','').strip() or 'exist' in step.get('observation','')[:130]:
   print('rawStep',str({k:v for k,v in step.items() if k in ('action','observation','state','extra_info')})[:490])
 hist=s['history'];print('hist tools')
 for t in hist:
  if t['role']=='tool' and ('returncode' in str(t).lower() or 'output' in str(t['content']).lower() or len(str(t['content']))<90):
   print(str(t)[:385])
   break
 print('hist examples',[(k,t[k]) for k in t if k not in ('content','message','agent')]);print('hash',__import__('hashlib').sha256(raw).hexdigest())
