"""Verify the release with Python 3.11+ standard library only; no model, GPU or dataset required."""
from pathlib import Path
from collections import defaultdict
from statistics import mean
import hashlib,gzip,json
ROOT=Path(__file__).resolve().parent
def get(p):
    src=p.read_bytes()
    return json.loads(gzip.decompress(src) if p.suffix=='.gz' else src)
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def merged(spans):
    parts=defaultdict(list)
    for s in spans:parts[s['event_id'],s['json_pointer']].append((s['char_start'],s['char_end']))
    unique={}
    for key,intervals in parts.items():
        dest=[]
        for a,b in sorted(intervals):
            if dest and a<=dest[-1][1]:dest[-1]=(dest[-1][0],max(dest[-1][1],b))
            else:dest.append((a,b))
        unique[key]=dest
    return unique
def metric(gold,selected):
    spans=[s for n in selected for s in n['source_spans']];recovered=merged(spans)
    common=sum(max(0,min(b,v)-max(a,u)) for k,ints in gold.items() for a,b in ints for u,v in recovered.get(k,()))
    target=sum(b-a for ints in gold.values() for a,b in ints);display=sum(s['char_end']-s['char_start'] for s in spans)
    coverage=common/target;density=common/display if display else 0.
    return dict(coverage=coverage,density=density,f1=2*coverage*density/(coverage+density) if common else 0,
                full_support=int(common==target),nodes=len(selected),tokens=sum(n['token_count'] for n in selected))
def pack(order,pool,calls,how,budget=2048):
    used=0;selected=[]
    for place,k in enumerate(order):
        n=pool[k]['token_count']
        if n+used>budget:break
        used+=n;selected.append(k)
    else:return selected
    if how=='prefix':return selected
    tail=order[place:]
    if how=='related':
        other={'content.tool_output':'content.tool_argument','content.tool_argument':'content.tool_output'}
        links={(call,kind) for k in selected for call,kind in [calls[k]] if call}
        tail=sorted(tail,key=lambda k:(calls[k][0],other.get(calls[k][1])) not in links)
    for k in tail:
        n=pool[k]['token_count']
        if used+n<=budget:selected.append(k);used+=n
    return selected
def check(result,record):
    assert all(abs(x-record[k])<1e-12 for k,x in result.items())
