"""Declared follow-up. Only historical verdicts and six shared probes enter the writer."""
import csv,gzip,hashlib,io,itertools,json,math,random,struct,sys,zipfile
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from prepare import SYSTEMS,ts,add_event
from policy import order

def collect():
    raw=ROOT.parent/'raw'/'west.zip';source=json.loads((ROOT.parent/'source.json').read_bytes());assert hashlib.sha256(raw.read_bytes()).hexdigest()==source['west.zip']['sha256']
    sessions={};ident={}
    with zipfile.ZipFile(raw) as z,z.open('test-results.csv') as f:
        for r in csv.DictReader(io.TextIOWrapper(f),delimiter='\t'):
            setting=r['rel']+r['sessiontype']
            if r['system'] not in SYSTEMS or setting not in ('BN','MI'):continue
            name=(r['tid'],r['parameters']);test=ident.setdefault(name,len(ident))
            start=ts(r['sstarted']);t=ts(r['ostarted']) if r['ostarted'] not in ('NULL','') else start
            def duration(s):return int(s) if s.isdigit() else 0
            end=max(start+duration(r['sduration']),t+duration(r['oduration']))
            add_event(sessions,(setting,r['system'],int(r['jid'])),start,end,test,(t,int(r['oid'])),int(r['result']))
    groups=defaultdict(list)
    for (setting,s,i),v in sessions.items():
        ys={t:int(o in (1,2)) for t,(_,o) in v['events'].items() if o!=3}
        groups[setting,s].append((v['start'],v['end'],i,ys))
    return groups

def decide(history,roster,probes,vals):
    pending=sorted(set(roster)-set(probes));ids=pending+probes;n=len(pending);k=math.ceil(n*.1)
    tab=np.array([[r.get(i,-1) for i in ids] for r in history]);ok=(tab>=0).astype(float);fail=(tab==1).astype(float)
    age=2**(np.arange(-14,1,dtype=float)/4);global_risk=(fail.sum()+1)/(ok.sum()+2)
    static=(age@fail+2*global_risk)/(age@ok+2);mod=np.where(tab[:,n:]<0,1.,np.where(tab[:,n:]==vals,2.,.5))
    def pred(mask):
        w=age*mod[:,mask].prod(axis=1)
        risk=(w@fail[:,:n]+2*static[:n])/(w@ok[:,:n]+2)
        return risk,order(risk)
    extra=tuple(range(4));common=(4,5);full=tuple(range(6))
    risk,fullrank=pred(full)
    cands={p:pred(p+common)[1] for b in (0,1,2) for p in itertools.combinations(extra,b)}
    fixed=max((p for p in cands if len(p)==2),key=lambda p:(round(float(risk[cands[p][:k]].sum()),12),p))
    decision=set(cands[fixed][:k])
    minimal=min((p for p in cands if set(cands[p][:k])==decision),key=lambda p:(len(p),p))
    novelty=[1-static[n+i] if vals[i] else static[n+i] for i in extra]
    ranked=sorted(extra,key=lambda i:(novelty[i],i),reverse=True)
    def surprise(q):return tuple(sorted(ranked[:q]))
    opts={'fixed':fixed,'minimal':minimal,'full':extra,'zero':(),'surprise2':surprise(2),'recent2':(2,3),'oracle_len_surprise':surprise(len(minimal))}
    for q in (0,1,2):
        opts['surprise'+str(q)]=surprise(q)
        opts['recent'+str(q)]=tuple(range(4-q,4))
    methods={}
    for name,p in opts.items():
        rank=fullrank if name=='full' else cands[p]
        packet=b''.join([bytes([len(p)])]+[struct.pack('>HB',probes[i],vals[i]) for i in p])
        methods[name]={'packet':packet.hex(),'chosen':[pending[int(j)] for j in rank[:k]],'rank':[pending[int(j)] for j in rank]}
    return methods

def histories(groups):
    for (setting,s),rs in sorted(groups.items()):
        rs=sorted(rs,key=lambda x:(x[0],x[2]))
        for j,(start,end,i,ys) in enumerate(rs):
            if j<len(rs)-300 or len(ys)<8:continue
            hist=sorted((r for r in rs[:j] if r[1]<start),key=lambda x:(x[1],x[2]))[-15:]
            if len(hist)<15:continue
            probes=sorted(ys,key=lambda t:hashlib.sha256(f's5-transfer|{setting}|{s}|{i}|{t}'.encode()).digest())[:6]
            vals=[ys[t] for t in probes];method=decide([r[3] for r in hist],sorted(ys),probes,vals)
            yield {'setting':setting,'system':s,'id':i,'history':[r[2] for r in hist],'probes':list(zip(probes,vals)),'methods':method}

def main():
    groups=collect();res=list(histories(groups))
    grouped=defaultdict(list)
    for r in res:grouped[r['setting'],r['system']].append(r)
    for key,rs in grouped.items():
        lens=[len(bytes.fromhex(r['methods']['minimal']['packet']))//3 for r in rs]
        random.Random('s5-size-control|'+str(key)).shuffle(lens)
        for r,q in zip(rs,lens):
            for name in ('surprise','recent'):r['methods']['matched_'+name]=r['methods'][name+str(q)]
    data=b'\n'.join(json.dumps(r,separators=(',',':')).encode() for r in res)
    # Freeze the materialized packet/decision roster before joining current outcomes.
    dest=ROOT/'outputs.jsonl.gz';dest.write_bytes(gzip.compress(data,compresslevel=3,mtime=0))
    (ROOT/'lock.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'PROTOCOL.md',ROOT/'run.py',dest)},indent=1))
    print('decision rows',len(res));score(groups,res)
def score(groups,res):
    truth={(setting,s,i):ys for (setting,s),rs in groups.items() for _,_,i,ys in rs}
    stats=defaultdict(lambda:defaultdict(list));per=[]
    for r in res:
        y=truth[r['setting'],r['system'],r['id']];m=r['methods']
        assert set(m['fixed']['chosen'])==set(m['minimal']['chosen'])
        remaining=sum(y.values())-sum(v for _,v in r['probes'])
        for k,md in m.items():
            hits=sum(y[i] for i in md['chosen']);b=len(bytes.fromhex(md['packet']))
            v=(hits/remaining if remaining else None,b,hits,remaining)
            stats[r['setting'],r['system']][k].append(v)
            per.append([r['setting'],r['system'],r['id'],k,*v])
    (ROOT/'per_cycle.json.gz').write_bytes(gzip.compress(json.dumps(per,separators=(',',':')).encode(),mtime=0))
    out={}
    for (setting,s),mm in stats.items():
        sm={}
        for k,vs in mm.items():
            recalls=[v[0] for v in vs if v[0] is not None]
            sm[k]={'recall':float(np.mean(recalls)) if recalls else None,'bytes':sum(v[1] for v in vs),'n':len(vs),'hits':sum(v[2] for v in vs),'qualifying':len(recalls),'length_counts':dict(Counter((v[1]-1)//3 for v in vs))}
        out.setdefault(setting,{})[s]=sm
    (ROOT/'results.json').write_text(json.dumps(out,indent=1))
    (ROOT/'coverage.json').write_text(json.dumps({mode:{s:{'raw_sessions':len(groups.get((mode,s),[])),'eligible_sessions':len(stats.get((mode,s),{}).get('fixed',[]))} for s in sorted(SYSTEMS)} for mode in ('BN','MI')},indent=1))
    for setting,x in out.items():
        print(setting,len(x),'sessions',sum(sys['fixed']['n'] for sys in x.values()),'bytes',sum(sys['minimal']['bytes'] for sys in x.values()),'of',sum(sys['fixed']['bytes'] for sys in x.values()))
if __name__=='__main__':main()
