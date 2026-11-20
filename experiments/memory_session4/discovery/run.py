import gzip,hashlib,json
from pathlib import Path
from memory import State,load_rows,shard,suggest,train
from fetch import ROOT,SPLITS
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,sort_keys=True,indent=1))
def main():
    locks=json.loads((ROOT/'projection_hashes.json').read_bytes());assert all(sha(ROOT/k)==v for k,v in locks.items())
    trainset=load_rows('train');tables=train(trainset);save(ROOT/'trained_tables.json',tables)
    pre=['PROTOCOL.md','ADDENDUM-before-outcomes.md','fetch.py','project.py','memory.py','run.py','metrics.py','sources.json','projection_hashes.json','trained_tables.json']
    save(ROOT/'input_lock.json',{'files':{k:sha(ROOT/k) for k in pre},'train_demo_groups':[sum(shard(k)!=0 for k in trainset),sum(shard(k)==0 for k in trainset)]})
    roster={};previous=set(trainset)
    with (ROOT/'predictions.jsonl.gz').open('wb') as fp,gzip.GzipFile(fileobj=fp,mode='wb',mtime=0,filename='') as out:
        for split in SPLITS[1:]:
            demos=load_rows(split)
            assert not set(demos)&set(trainset)
            roster[split]={'n_demos':len(demos),'previous_split_intersection':len(set(demos)&previous)}
            previous.update(demos)
            for demo,rows in demos.items():
                st=State()
                for r in rows:
                    turn=r['turn'];c=r['c']
                    pred=suggest(st,turn,c,r['lex'],tables)
                    metadata={'last_from':st.last[1] if st.last else None,'focus_from':st.focus[1] if st.focus else None}
                    row={'s':split,'d':demo,'i':turn,'pred':pred,**metadata}
                    out.write((json.dumps(row,separators=(',',':'))+'\n').encode())
                    st.observe(turn,c,r['k'],r['y'])
    save(ROOT/'output_lock.json',{'sources':roster,'files':{k:sha(ROOT/k) for k in ('input_lock.json','predictions.jsonl.gz')}})
if __name__=='__main__':main()
