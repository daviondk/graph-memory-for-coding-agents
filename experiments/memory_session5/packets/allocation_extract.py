from transfer_extract import *
def main():
    refs=json.loads((ROOT/'shards.json').read_bytes());candidates=defaultdict(list);old=json.loads((ROOT/'selection.json').read_bytes());forbidden={s for rs in old.values() for s,k,i in rs}|{s for s,k,i in json.loads((ROOT/'transfer/selection.json').read_bytes())};out=ROOT/'allocation';out.mkdir(exist_ok=True)
    for k,it in enumerate(refs):
        pf=pq.ParquetFile(OLD/'.scratch'/Path(it['path']).name);i=0
        for batch in pf.iter_batches(batch_size=1000,columns=['instance_id','traj_id']):
            for row in batch.to_pylist():
                s=row['instance_id'];repo=s.split('.')[0]
                if repo in ALLOWED and s not in forbidden and int(h('s5-repo|'+repo),16)%3!=0 and int(h('compact-s4|'+s),16)%10!=0 and s!='django-money__django-money.835c1ab8.func_pm_ctrl_shuffle__viqnyl9u':
                    candidates[s].append((h('s5-alloc-traj|'+str(row['traj_id'])+'|'+str(k)+'|'+str(i)),k,i))
                i+=1
        pf.close()
    chosen=[(s,*min(candidates[s])[1:]) for s in sorted(candidates,key=lambda s:h('s5-alloc-confirm|'+s))[:650]];index={(k,i):s for s,k,i in chosen}
    dump('allocation/selection.json',chosen);counts=Counter();(out/'source').mkdir(exist_ok=True)
    for k,it in enumerate(refs):
        pf=pq.ParquetFile(OLD/'.scratch'/Path(it['path']).name);idx=0
        with gzip.open(out/'source'/f'{k}.jsonl.gz','wt',encoding='utf8',compresslevel=3) as f:
            for b in pf.iter_batches(batch_size=24,columns=['instance_id','traj_id','messages','model'],use_threads=False):
                for j in range(b.num_rows):
                    if (k,idx) in index:
                        r=b.slice(j,1).to_pylist()[0];obj=decode(r,k,idx)
                        if obj is not None:print(json.dumps(obj,ensure_ascii=True,separators=(',',':')),file=f);counts[obj['format']]+=1
                        else:counts['excluded']+=1
                    idx+=1
        pf.close()
    dump('allocation/extraction.json',dict(counts));print(dict(counts))
if __name__=='__main__':main()
