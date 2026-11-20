import collections, concurrent.futures, gzip, hashlib, json, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
OLD=HERE.parents[1]/'graph_memory_round4'/'writer'
sys.path.insert(0,str(OLD/'source_kimi'))
from acquire_k import grab, RUN, A,B,D,save,sha,read,write
pool={r['instance_id']:r for p in (A,B,D) for r in read(p/'selection.json')}
old={r['instance_id'] for r in read(D/'source_kimi'/'selection.json')}
by=collections.defaultdict(list)
for key in sorted(pool.keys()-old,key=lambda x:hashlib.sha256(('R5-schema|'+x).encode()).hexdigest()):
    by[pool[key]['repo']].append(pool[key])
roster=[by[k][j] for j in range(16) for k in sorted(by) if j<len(by[k])][:120]
save(HERE/'roster.json',roster); assert not old.intersection(q['instance_id'] for q in roster)
save(HERE/'roster_lock.json',dict(protocol=sha(HERE/'PROTOCOL.md'),generator=sha(__file__),roster=sha(HERE/'roster.json'),run=RUN,previous=len(old),n=len(roster)))
def main():
    receipts=[]; hist=collections.Counter()
    files=[gzip.open(HERE/f'source_{j}.jsonl.gz','wt',encoding='utf8') for j in range(8)]
    try:
        with concurrent.futures.ThreadPoolExecutor(10) as ex:
            for j,(q,r) in enumerate(ex.map(grab,roster)):
                receipts.append(r); hist[r['status']]+=1
                if q:write(files[j%8],q)
                if (j+1)%20==0: print(j+1,hist,flush=True)
    finally:
        for fp in files:fp.close()
    save(HERE/'receipts.json',receipts)
    print(len(roster),hist,flush=True)
if __name__=='__main__':main()
