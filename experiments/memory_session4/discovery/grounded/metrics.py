from collections import Counter,defaultdict
from pathlib import Path
import csv,json,hashlib,random,sys
ROOT=Path(__file__).resolve().parent
ARMS=['baseline','blind','member','visible']
def read(n):return json.loads((ROOT/n).read_bytes())
def compute():
    for lock in ('input_lock.json','output_lock.json'):
        assert all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h for f,h in read(lock).items())
    key=lambda r:(r['s'],r['d'],r['i']);q={key(r):r for r in read('queries.json')};states={};files=[]
    for f in sorted((ROOT/'receipts').glob('*.json')):
        j=json.loads(f.read_bytes());files+=j['file_receipts']
        for r in j['probes']:assert key(r) not in states;states[key(r)]=r
    assert states.keys()==q.keys()
    groups=defaultdict(lambda:defaultdict(list));casewise=[]
    for r in read('oracle.json'):
        if r['a'] not in ('click','submit','text_input','change') or not r['y']:continue
        k=key(r);b=r['base'];pred={a:b for a in ARMS};st=states.get(k)
        if st:
            query=q[k];assert query['orig']==b and query['from']<r['i']
            old=query['old'];pred['blind']=old
            if st['present']:pred['member']=old
            if st['visible']:pred['visible']=old
        hits={a:int(v==r['y']) for a,v in pred.items()}
        hits.update({'n':1,'probed':int(bool(st)),'successful_probe':int(st is not None and st['present'] is not None),'visible_probe':int(bool(st and st['visible']))})
        for a in ARMS[1:]:
            hits['W_'+a]=int(hits[a]>hits['baseline']);hits['L_'+a]=int(hits[a]<hits['baseline'])
        groups[r['s']][r['d']].append(hits)
        if st:casewise.append({**r,**st,'suggested':q[k]['old'],**hits})
    out={'cost':{'requests':len(files),'response_codes':dict(Counter(str(x.get('http',x.get('error'))) for x in files)),
        'wire_body_bytes':sum(x.get('wire_bytes',0) for x in files),'probes_all_kinds':len(q)}}
    for split,gs in groups.items():
        by_d={}
        for d,rows in gs.items():
            c=Counter()
            for r in rows:c.update(r)
            by_d[d]=c
        x=Counter()
        for c in by_d.values():x.update(c)
        res=dict(x);res['demos']=len(gs);res['ci']={}
        for a in ARMS[1:]:
            pairs=[(v[a]-v['baseline'],v['n']) for v in by_d.values()];rng=random.Random(17112026);deltas=[]
            for _ in range(2000):
                sample=rng.choices(pairs,k=len(pairs));deltas.append(sum(x[0] for x in sample)/sum(x[1] for x in sample))
            deltas.sort();res['ci'][a]=[deltas[49],deltas[1949]]
        out[split]=res
    if '--verify' in sys.argv:assert out==read('results.json')
    else:
        (ROOT/'results.json').write_text(json.dumps(out,indent=1))
        (ROOT/'cases.json').write_text(json.dumps(casewise,separators=(',',':')))
    print(out)
if __name__=='__main__':compute()

