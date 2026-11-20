"""Convert verified publisher inputs to anonymized chronological test-cycle observations."""
import csv,gzip,hashlib,io,json,zipfile
from pathlib import Path
from datetime import datetime
from collections import defaultdict
ROOT=Path(__file__).resolve().parent
SYSTEMS={'system'+str(n) for n in (11,13,21,28,30,33,46,64,96)}

def save(name,x):
    (ROOT/name).write_bytes(gzip.compress(json.dumps(x,separators=(',',':')).encode(),mtime=0))
def ts(s):return int((datetime.fromisoformat(s)-datetime(1970,1,1)).total_seconds())
def add_event(rows,key,start,end,test,order,verdict):
    session=rows.setdefault(key,{'start':start,'end':end,'events':{}})
    session['end']=max(session['end'],end)
    prior=session['events'].get(test)
    if prior is None or order>prior[0]:session['events'][test]=(order,verdict)
def main():
    raw=ROOT/'raw';rows={};test_ids={}
    for name,obj in json.loads((ROOT/'source.json').read_bytes()).items():assert hashlib.sha256((raw/name).read_bytes()).hexdigest()==obj['sha256']
    with zipfile.ZipFile(raw/'west.zip') as z,z.open('test-results.csv') as f:
        for r in csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig'),delimiter='\t'):
            if r['system'] not in SYSTEMS or r['sessiontype']!='N' or r['rel']!='M':continue
            start=ts(r['sstarted']);time=ts(r['ostarted']) if r['ostarted'] not in ('NULL','') else start
            def seconds(t):
                try:return int(t)
                except ValueError:return 0
            end=max(start+seconds(r['sduration']),time+seconds(r['oduration']))
            test_key=(r['tid'],r['parameters']); test_id=test_ids.setdefault(test_key,len(test_ids))
            add_event(rows,(r['system'],int(r['jid'])),start,end,test_id,(time,int(r['oid'])),int(r['result']))
    for name in ('paintcontrol','iofrol'):
        with (raw/(name+'.csv')).open(encoding='utf-8-sig') as f:
            for r in csv.DictReader(f,delimiter=';'):
                cycle=int(r['Cycle']);add_event(rows,(name,cycle),cycle,cycle,int(r['Name']),int(r['Id']),int(r['Verdict']))
    corpus=defaultdict(list)
    for (sys,i),r in rows.items():
        ys=sorted((test,int(y in (1,2))) for test,(_,y) in r['events'].items() if y!=3)
        corpus[sys].append({'id':i,'start':r['start'],'end':r['end'],'tests':ys})
    for sys in corpus:corpus[sys].sort(key=lambda s:(s['start'],s['id']))
    save('cycles.json.gz',corpus)
    print({s:(len(v),sum(len(r['tests']) for r in v)) for s,v in corpus.items()})
if __name__=='__main__':main()
