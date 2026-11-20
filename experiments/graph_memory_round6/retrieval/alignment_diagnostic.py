"""Exploratory contrasts after inspecting the first R6 panel, prior to Python archive replication."""
from collections import defaultdict
from grade import stats
from run import D,readgz,save
rows=defaultdict(list)
for r in readgz(D/'paired.jsonl.gz'):
    if 'r4_alignment' in r['ranks']:
        ranks=dict(r['ranks'],full=r['ranks']['r4_alignment'],original_full=r['ranks']['full'])
        rows[r['stage']+'_'+r['panel'].split('_')[0]].append(dict(r,ranks=ranks))
out={p:stats(v) for p,v in rows.items()}
save('alignment_diagnostic.json',out)
for p,v in out.items():
    a=v['diff']['full-r4']
    print(p,[round(100*a[k][0],2) for k in ('delta','lo','hi')],a['wins'],a['losses'])

