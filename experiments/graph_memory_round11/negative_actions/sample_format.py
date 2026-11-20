import gzip,json,collections,re
from pathlib import Path
d=Path(__file__).resolve().parent
rows=collections.defaultdict(list);ct=collections.Counter()
for f in (d/"observations").glob("*.gz"):
 for v in json.loads(gzip.decompress(f.read_bytes()))['steps']:
  if not v:continue
  s=v['args'];raw=v['raw'];seen=v['seen'];cmd=s.get('command','');kind=s.get('command')
  if raw is None or seen is None:continue
  if v['tool'] in ('bash','functions.bash') and re.match(r'^(?:grep|rg|find|ls|cat|test)\b',cmd) and (len(raw.strip())<15 or 'exit code' in seen or 'No such file' in raw):
   cat='shell '+str(re.sub(r"[0-9]+","N",seen)[0:75]);ct[cat]+=1
   if len(rows[cat])<1:rows[cat].append([cmd,raw,seen])
  if 'editor' in v['tool'] and (not raw.strip() or re.search(r"does not exist|No such file|doesn't exist|not found",raw[:260],re.I)) and kind=='view':
   cat='editor';ct[cat]+=1
   if len(rows[cat])<3:rows[cat].append([s,raw,seen])
print(ct.most_common(12))
for k,v in rows.items():
 print(k, str(v)[:400])
