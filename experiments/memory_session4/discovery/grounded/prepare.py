import gzip,hashlib,json,re,sys
from pathlib import Path
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT.parent))
from memory import State
from project import project
from fetch import REV,REPO
SPLITS=['valid','test_iid','test_web']
def token(x):return hashlib.sha256(x.encode()).hexdigest()
def sha(x):return hashlib.sha256(x).hexdigest()
def save(n,x):(ROOT/n).write_text(json.dumps(x,separators=(',',':')))
def make():
    roster={};queries=[];labels=[];sources=[]
    for s in SPLITS:
        path=ROOT.parent/'raw'/(s+'.json.gz')
        url='https://huggingface.co/datasets/'+REPO+'/resolve/'+REV+'/data/chat/'+s+'.json.gz'
        data=path.read_bytes() if path.exists() else urlopen(url,timeout=120).read()
        sources.append({'url':url,'sha':sha(data)})
        demos={}
        for line in gzip.decompress(data).splitlines():
            raw=json.loads(line);r=project(raw)
            m=re.search(r'(\d+)h x (\d+)w',raw['viewport'] or '')
            r['vw']=int(m[2]) if m else None;r['vh']=int(m[1]) if m else None
            demos.setdefault(r['demo'],[]).append(r)
        eligible={};all_labels={}
        for d,rows in demos.items():
            st=State();op=[];ys=[]
            for r in sorted(rows,key=lambda q:q['turn']):
                turn=r['turn'];c=r['c'];uids=[u for u,t,b in c];old=st.last
                isedit=old is not None and old[2]=='click' and old[3]
                baseline=old[0] if isedit and old[0] in uids else uids[0] if uids else None
                if isedit and uids and old[0] not in uids:
                    op.append({'s':s,'d':d,'i':turn,'old':old[0],'orig':baseline,'from':old[1],'w':r['vw'],'h':r['vh']})
                ys.append({'s':s,'d':d,'i':turn,'a':r['k'],'y':r['y'],'base':baseline})
                st.observe(turn,c,r['k'],r['y'])
            if op:eligible[d]=op;all_labels[d]=ys
        sample=sorted(eligible,key=lambda d:token('memory4-ground/'+d))[:90]
        roster[s]={'sampled':sample,'all_demos':len(demos),'eligible_demos':len(eligible),'eligible_turns_all':sum(map(len,eligible.values()))}
        for d in sample:queries+=eligible[d];labels+=all_labels[d]
    save('queries.json',queries);save('oracle.json',labels);save('sources.json',sources);save('roster.json',roster)
    init=['PROTOCOL.md','prepare.py','collect.py','metrics.py','queries.json','sources.json','roster.json']
    save('input_lock.json',{x:sha((ROOT/x).read_bytes()) for x in init})
    print([(s,len(roster[s]['sampled']),roster[s]['eligible_turns_all']) for s in SPLITS],len(queries))
if __name__=='__main__':make()

