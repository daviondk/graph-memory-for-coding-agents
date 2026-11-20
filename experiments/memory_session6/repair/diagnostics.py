from collections import Counter
import re
import statistics
from common import *
def main():
    items=read('roster.json')['items']; prefixes=[read(path(r['id'],'prefix.json')) for r in items]
    responses=[read(p.relative_to(ROOT)) for p in (ROOT/'calls').glob('*.json.gz')]
    branches=[read(path(r['id'],b+'.json')) for r in items for b in ('note','raw','current')]
    norm=lambda s:' '.join(re.sub(r'https?://\S+','',s).casefold().split()).strip(' .')
    old=[(ROOT/path(r['id'],'old.txt')).read_bytes().decode() for r in items]
    cur=[(ROOT/path(r['id'],'current.txt')).read_bytes().decode() for r in items]
    stats=dict(ambiguity_counts=dict(Counter(p['ambiguity'] for p in prefixes)),raw_was_complete=sum(p['raw']==s for p,s in zip(prefixes,old)),note_count=len(items),weak_normalization_equivalent_among_changed=sum(a!=b and norm(a)==norm(b) for a,b in zip(old,cur)),unique_finishes=dict(Counter(d['response']['choices'][0]['finish_reason'] for d in responses)),reader_logical_finishes=dict(Counter(read('calls/'+b['call']+'.json.gz')['response']['choices'][0]['finish_reason'] for b in branches)),first_native=min(d['start'] for d in responses),final_native_start=max(d['start'] for d in responses),total_reply_calls=len(responses))
    peak=[]
    for row in (ROOT/'runtime/gpu_samples.jsonl').read_bytes().splitlines():
        parts=json.loads(row)['nvidia_smi'].split(',');peak.append([int(parts[2]),int(parts[3]),float(parts[4])])
    stats['gpu_sampling']={'observations':len(peak),'peak_vram_mib':max(r[0] for r in peak),'max_recorded_utilization_pct':max(r[1] for r in peak),'median_sampled_power_w':statistics.median(r[2] for r in peak)}
    save('diagnostics.json',stats)
    print(canonical(stats))
if __name__=='__main__':main()

