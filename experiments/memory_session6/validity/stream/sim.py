"""Replay actual first-parent changes through a mutable note. Both directions charge emitted application bytes."""
import collections,copy,gzip,hashlib,json,struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from policy import Sketch,vi
from prepare import ROOT,emit,h
BASE=ROOT/'stream'
def load(path):return json.loads(gzip.decompress(path.read_bytes()))
def packet(groups,method):
    if not groups:return b''
    out=bytearray(vi(len(groups)))
    for slot,entries in groups:
        out.extend(bytes.fromhex(slot) if method=='bloom' else vi(slot));out.extend(vi(len(entries)))
        for path,val in entries:
            if method=='flips':out.extend(vi(2*path+int(val)))
            else:out.extend(vi(path)+vi(2*val if val>=0 else -2*val-1))
    return bytes(out)
def unpack(raw,method):
    if not raw:return []
    it=iter(raw)
    def vint():
        n=0
        for k in range(12):
            b=next(it);n|=(b&127)<<(7*k)
            if b<128:return n
        raise ValueError()
    n=vint();out=[]
    for _ in range(n):
        slot=bytes(next(it) for _ in range(12)).hex() if method=='bloom' else vint();entries=[]
        for _ in range(vint()):
            p=vint()
            if method=='flips':entries.append((p//2,bool(p%2)))
            else:
                val=vint();entries.append((p,val//2 if val%2==0 else -(val//2)-1))
        out.append((slot,entries))
    assert next(it,None) is None
    return out
def simulate(repo,initial,events,oracle,rate):
    keys=[r['key'] for r in initial['watch']];idx={t:i for i,t in enumerate(keys)};u=len(keys)
    counts=copy.deepcopy(initial['initial_counts'])
    paths=sorted(set(p for vals in counts.values() for p in vals));pidx={p:i for i,p in enumerate(paths)}
    cur={arm:copy.deepcopy(counts) for arm in ('delta','bloom')}
    sets={arm:{t:set(v) for t,v in counts.items()} for arm in ('flips','pull','lease','local','signed')}
    dirty={arm:{t:set() for t in keys} for arm in ('local','signed')};seen={'local':set(),'signed':set()}
    b=Sketch(32,'net')
    for t in keys:b.add('','+',t)
    lengths=sum(1+q['chars'] for q in initial['watch'])
    # Common path IDs are shared via the old observations and changed-path feed. Exact names/values to enroll are costed.
    countsreg=len(vi(u))+sum(len(vi(len(vals)))+sum(len(vi(pidx[p]))+len(vi(n)) for p,n in vals.items()) for vals in counts.values())
    extra_paths=sum(len(vi(len(s.encode())))+len(s.encode()) for s in paths)
    startup={'flips':1+lengths+countsreg,'pull':1+lengths+countsreg,'lease':1+lengths+countsreg,'delta':1+lengths,'bloom':32,'local':0,'signed':0}
    sums={arm:collections.Counter({'enrollment_bytes':n,'traffic':n}) for arm,n in startup.items()};last={t:-100 for t in keys};live_oids={};receipts=[]
    for step,(event,truth) in enumerate(zip(events,oracle),start=1):
        files=event['files'];order=sorted(keys,key=lambda t:h(f's6-ask|{repo}|{step}|{t}'))
        qs=order[:(0 if rate=='sparse' and step%4 else 8 if rate=='dense' else 1)]
        ordered=[];updates=collections.defaultdict(list);deltas=collections.defaultdict(list);broadcast=collections.defaultdict(list)
        sketch=Sketch(512,'signed')
        for file in files:
            p=file['p'];live_oids[p]=(file['oid'],file['new_bytes'])
            if p not in pidx:pidx[p]=len(paths);paths.append(p)
            j=pidx[p]
            for t,d in file['net'].items():
                sketch.add(p,'+' if d>0 else '-',t)
                if b.upper('','+',t):broadcast[t].append((j,d))
                if t not in idx:continue
                old=counts[t].get(p,0);new=old+d;assert new>=0
                if new:counts[t][p]=new
                else:counts[t].pop(p,None)
                if bool(old)!=bool(new):updates[idx[t]].append((j,bool(new)))
                deltas[idx[t]].append((j,d))
        def wire(arm,items,kind):
            data=packet(sorted(items.items()),kind);sums[arm]['traffic']+=len(data);sums[arm]['update_bytes']+=len(data);sums[arm]['messages']+=int(bool(data))
            ordered.append([arm,kind,data.hex()])
            for k,changes in unpack(data,kind):
                t=k if kind=='bloom' else keys[k]
                if t not in idx:continue
                for j,x in changes:
                    p=paths[j]
                    if kind=='flips':
                        if x:sets[arm][t].add(p)
                        else:sets[arm][t].discard(p)
                    else:
                        n=cur[arm][t].get(p,0)+x;assert n>=0
                        if n:cur[arm][t][p]=n
                        else:cur[arm][t].pop(p,None)
        wire('flips',updates,'flips');wire('delta',deltas,'delta');wire('bloom',broadcast,'bloom')
        wire('lease',{i:z for i,z in updates.items() if step-last[keys[i]]<=4},'flips')
        for arm in ('pull','lease'):
            asking=qs if arm=='pull' else [t for t in qs if step-last[t]>4]
            if asking:
                request=vi(len(asking))+b''.join(vi(idx[t]) for t in asking)
                sums[arm]['traffic']+=len(request)+1;sums[arm]['request_ack_bytes']+=len(request)+1;sums[arm]['roundtrips']+=1
                groups={}
                for t in asking:
                    before=sets[arm][t];now=set(counts[t])
                    if before!=now:groups[idx[t]]=sorted((pidx[p],p in now) for p in before^now)
                wire(arm,groups,'flips')
        if files:
            payload=1+len(sketch.bits) if any(f['net'] for f in files) else 1
            sums['signed']['traffic']+=payload;sums['signed']['update_bytes']+=payload
        for arm in dirty:
            for t in keys:
                for f in files:
                    p=f['p']
                    if not f['new_bytes']:
                        sets[arm][t].discard(p);dirty[arm][t].discard(p);continue
                    if arm=='local' or sketch.upper(p,'-' if p in sets[arm][t] else '+',t):dirty[arm][t].add(p)
            for t in qs:
                for p in sorted(dirty[arm][t]):
                    oid,nb=live_oids[p];assert nb>0
                    sums[arm]['logical_file_reads']+=1
                    if oid not in seen[arm]:
                        sums[arm]['source_bytes']+=nb;sums[arm]['physical_blobs']+=1;seen[arm].add(oid)
                    # Only the requested file's actual current membership is returned to this simulated read.
                    if p in truth[t]:sets[arm][t].add(p)
                    else:sets[arm][t].discard(p)
                dirty[arm][t].clear()
        for arm,z in cur.items():assert z==truth
        assert counts==truth and all(sets['flips'][t]==set(truth[t]) for t in keys)
        for arm in sets:
            for t in qs:assert sets[arm][t]==set(truth[t]),(repo,step,t,arm)
        for t in qs:last[t]=step
        receipts.append({'step':step,'queries':qs,'messages':ordered,'snapshot':{a:dict(v) for a,v in sums.items()}})
    for v in sums.values():v['queries']=sum(len(r['queries']) for r in receipts);v['commits']=len(events);v['shared_initial_dict_bytes_if_required']=extra_paths
    return {arm:dict(z) for arm,z in sums.items()},receipts
def compute():
    catalog=load(BASE/'initial.json.gz');alltotals={};receipts=[]
    for r,initial in catalog.items():
        fn=r.replace('/','__');events=load(BASE/(fn+'_events.gz'));oracle=load(BASE/(fn+'_truth.gz'))
        for regime in ('sparse','regular','dense'):
            out,log=simulate(r,initial,events,oracle,regime);alltotals[r,regime]=out
            receipts.extend({'repo':r,'rate':regime,**z} for z in log)
    summary={}
    for rate in ('sparse','regular','dense'):
        summary[rate]={a:dict(sum((collections.Counter(out[a]) for (r,k),out in alltotals.items() if k==rate),collections.Counter())) for a in out}
    return {'total':summary,'by_repo':{'|'.join(k):v for k,v in alltotals.items()}},receipts
if __name__=='__main__':
    d,r=compute()
    if '--verify' in sys.argv:
        assert load(BASE/'log.json.gz')==r and json.loads((BASE/'results.json').read_bytes())==d;print('PASS older release history, wire decoder, truth for all requests')
    else:
        (BASE/'log.json.gz').write_bytes(gzip.compress(emit(r).encode(),mtime=0));(BASE/'results.json').write_text(json.dumps(d,indent=1))
        for rate,vals in d['total'].items():print(rate,{k:(v.get('traffic',0),v.get('physical_blobs',0),v.get('roundtrips',0)) for k,v in vals.items()})
