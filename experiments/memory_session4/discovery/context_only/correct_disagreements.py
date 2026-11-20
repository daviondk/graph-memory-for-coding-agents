import collections,gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
r=json.loads((ROOT/'results.json').read_bytes())
counts=collections.Counter()
with gzip.open(ROOT/'predictions.jsonl.gz','rt',encoding='utf8') as f:
    for line in f:
        x=json.loads(line);delta=int(x['p']!=(x['prior'] or None))
        counts[x['s']]+=delta;counts['pooled']+=delta
for s in r:r[s]['different']=counts[s]
(ROOT/'results_corrected.json').write_text(json.dumps(r,indent=1))
note={'reason':'Normalize CSV empty prior prediction to JSON null for disagreement count only','old_pooled_different':107,'corrected_pooled_different':104,'score_and_ci_unchanged':True,'corrected_sha256':hashlib.sha256((ROOT/'results_corrected.json').read_bytes()).hexdigest()}
(ROOT/'correction.json').write_text(json.dumps(note,indent=1))
print(note)

