import csv,json,hashlib,os,sys,math,random,zipfile,statistics
from pathlib import Path
from collections import Counter
import pyarrow.parquet as pq
here=Path(__file__).resolve().parent
base=Path(os.environ.get('VIBE_BENCH_HOME','D:/CodexResearch/x20-official-vibe/VibeMemBench'))
sys.path.insert(0,str(base/'scripts'));sys.path.insert(0,str(here.parent/'vibe_memory'))
from policy import valid
from path_probe import extract
p=here/'predictions.jsonl'
assert hashlib.sha256(p.read_bytes()).hexdigest()==(here/'predictions.sha256').read_text().strip()
t=pq.read_table(base/'benchmark/test.parquet',columns=['instance_id','patch']).to_pylist()
def goldfiles(patch):
    p=[]
    for line in patch.splitlines():
        if line.startswith('--- '):
            key=line[4:].split('\t')[0].removeprefix('a/')
            if valid(key):p.append(key)
    return set(p)
gold={r['instance_id']:goldfiles(r['patch']) for r in t}
rows=[]; names=['candidate','single','freq','action_receipt','raw_bm25','echo_capped']
for line in p.open(encoding='utf8'):
    r=json.loads(line);iid=r['id'];g=gold[iid]
    row={'id':iid,'repo':r['repo'],'gold_n':len(g),'prior_oracle':int(bool(g&set(r['all_prior']))),'available_gold':len(g&set(r['all_prior']))}
    for m in names:
        if m in r:paths=r[m]
        else:
            s=base/'outputs/memory'/m/r['language']/iid/'memory.json'
            receipt=json.loads(s.read_text(encoding='utf8'))['retrieved']
            paths=list(extract(receipt[0]['content'],r['repo']))[:3] if receipt else []
        hits=len(g&set(paths))
        row.update({m:int(hits>0),m+'_hits':hits,m+'_slots':len(paths),m+'_paths':'|'.join(paths)})
    rows.append(row)
assert len(rows)==len(gold)==111
def stat(left,right):
    v=[r[left]-r[right] for r in rows]; n=len(v);w=v.count(1);l=v.count(-1);d=w+l
    grouped={}
    for r,x in zip(rows,v):
        a=grouped.setdefault(r['repo'],[0,0]);a[0]+=x;a[1]+=1
    bins=list(grouped.values());rng=random.Random(20261116);dist=[]
    for _ in range(20000):
        sample=rng.choices(bins,k=len(bins));dist.append(100*sum(z[0] for z in sample)/sum(z[1] for z in sample))
    dist.sort()
    return {'wins':w,'losses':l,'ties':n-d,'delta_pp':100*(w-l)/n,'cluster_interval_pp':[dist[499],dist[19499]],'p_exact_question':min(1,2*sum(math.comb(d,j) for j in range(min(w,l)+1))/(2**d)) if d else 1}
result={'n':len(rows),'repositories':len(set(r['repo'] for r in rows)),'eligible':sum(r['gold_n']>0 for r in rows),'prior_oracle':sum(r['prior_oracle'] for r in rows),'total_applicable_files':sum(r['gold_n'] for r in rows),'matched_historical_gold':sum(r['available_gold'] for r in rows),'per_method':{m:{'success':sum(r[m] for r in rows),'returned':sum(r[m+'_slots']>0 for r in rows),'mean_slots':sum(r[m+'_slots'] for r in rows)/len(rows),'micro_recall':sum(r[m+'_hits'] for r in rows)/sum(r['gold_n'] for r in rows),'macro_recall_all':sum(r[m+'_hits']/r['gold_n'] if r['gold_n'] else 0 for r in rows)/len(rows)} for m in names},'pairing':{m:stat('candidate',m) for m in names if m!='candidate'}}
with (here/'scores.csv').open('w',encoding='utf8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(here/'results.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result,indent=2))

