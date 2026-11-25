"""Evaluate two different observed read events. No reading of version IDs during prediction."""
from collections import Counter,defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from sources import C,D,read,dump,sha
from build_packets import order
from predict_flow import Origins
from score_flow import rates

def savegz(file,data):
    file.write_bytes(gzip.compress((json.dumps(data,separators=(',',':'),sort_keys=True)+'\n').encode(),mtime=0))
def rg(file):return json.loads(gzip.decompress(file.read_bytes()))

def predict():
    inp=read(D/'input-lock.json')
    assert inp['packets']==sha((C/'flow-packets.json').read_bytes())
    packets=read(C/'flow-packets.json')
    orig=rg(D/'predictions.json.gz')
    assert read(D/'prediction-lock.json')['predictions']==sha((D/'predictions.json.gz').read_bytes())
    originals={r['trace']:r for r in orig}
    source={r['trace']:r for r in read(D/'corpus-audit.json')}
    out=[];quality=Counter()
    for row in packets:
        tr=row['trace'];idx=Origins(row['events'])
        obj=read(C/(source[tr]['blob']+'.json'))
        types={order(k):v.get('rdt:type','unknown') for k,v in obj['activity'].items() if order(k) is not None}
        text=[]
        for event in originals[tr]['text']:
            t=event['t']
            selected={m:p for m,p in event['arms'].items() if m in ('symbol_latest','literal_latest','literal_retract','literal_append','symbol_sham_latest')}
            selected['symbol_latest_operations']=selected['symbol_latest'] if types[t] in ('Operation','Binding') else []
            text.append(dict(t=t,arms=selected))
        reads=defaultdict(lambda:defaultdict(list))
        for c in row['cards']:reads[c['base'][0]][c['consumer']].append(c)
        samples=[]
        for value,parts in sorted(reads.items()):
            reps=[]
            for _,cs in sorted(parts.items()):
                reps.append(min(cs,key=lambda c:c['id']))
                quality['same_value_same_action_cards_dropped']+=len(cs)-1
            quality['last_without_next']+=int(bool(reps))
            for c,n in zip(reps,reps[1:]):
                t0,t1=c['consumer'],n['consumer']
                cs=idx.earlier(0,value,t0)[0];ds=idx.earlier(0,value,t1)[0]
                assert cs and ds and cs==ds[:len(cs)] and t0<t1
                p=cs[-1]
                u0=len(cs)==1;u1=len(ds)==1
                b=[]
                for card in (c,n):
                    _,name,scope=card['base'];t=card['consumer']
                    v=idx.earlier(2,scope,t)[0] or idx.earlier(1,name,t)[0]
                    b.append(bool(v and v[-1]==p))
                arms={'one_early':[u0,u0],'one_late':[u1,u1],'two_unique':[u0,u1],'latest_at_query':[True,ds[-1]==p],
                      'one_early_last':[True,True],'one_false':[False,False],'binding_privileged':b}
                samples.append(dict(first=c['id'],next=n['id'],a=t0,b=t1,producer=p,counts=[len(cs),len(ds)],arms=arms))
        out.append(dict(trace=tr,rows=samples,text=text))
    p=D/'followup-forecasts.json.gz';savegz(p,out)
    dump(D/'followup-forecast-lock.json',dict(forecasts=sha(p.read_bytes()),source=sha((D/'input-lock.json').read_bytes()),source_predictions=sha((D/'predictions.json.gz').read_bytes()),protocol=sha((D/'followup-protocol.json').read_bytes()),code=sha(Path(__file__).read_bytes()),counts=quality))
    print('sealed',sum(len(z['rows']) for z in out),'successive reads')

def diagnostics(cells):
    result={}
    for model,byfam in cells.items():
        # [tp,fp,fn,tn,number of trials,number both correct]
        A=np.array(list(byfam.values()))
        v=A.sum(0);stats=rates(v[:3]);stats['tn']=int(v[3]);stats['trials']=int(v[4]);stats['both_accuracy']=v[5]/v[4] if v[4] else None
        for metric in ('precision','recall','f1'):
            vals=[rates(x[:3])[metric] for x in A];finite=[x for x in vals if x is not None]
            stats['macro_family_'+metric]=np.mean(finite) if finite else None
            stats['macro_defined_'+metric]=len(finite)
        result[model]=stats
    return result

def compare(cells,a,b):
    groups=sorted(cells[a])
    x=np.array([cells[a][g] for g in groups]);y=np.array([cells[b][g] for g in groups])
    draws=np.random.default_rng(2209).integers(0,len(groups),size=(5000,len(groups)))
    def M(ar):
        z=np.moveaxis(ar,-1,0)
        def ratio(a,b):return np.divide(a,b,out=np.full(a.shape,np.nan),where=b>0)
        return np.stack([ratio(z[0],z[0]+z[1]),ratio(z[0],z[0]+z[2]),ratio(2*z[0],2*z[0]+z[1]+z[2]),ratio(z[5],z[4])],axis=-1)
    d=M(x.sum(0))-M(y.sum(0));dist=M(x[draws].sum(1))-M(y[draws].sum(1))
    out={}
    for j,k in enumerate(('precision','recall','f1','both_accuracy')):
        v=dist[:,j];v=v[np.isfinite(v)];out[k]=dict(delta_pp=d[j]*100 if np.isfinite(d[j]) else None,ci_pp=(np.quantile(v,[.025,.975])*100).tolist() if len(v) else None)
    return out

def evaluate():
    lock=read(D/'followup-forecast-lock.json');fp=D/'followup-forecasts.json.gz';assert lock['forecasts']==sha(fp.read_bytes()) and lock['code']==sha(Path(__file__).read_bytes()) and lock['protocol']==sha((D/'followup-protocol.json').read_bytes())
    assert sha((C/'flow-gold.json').read_bytes())==read(D/'input-lock.json')['gold']
    gs={r['trace']:r['reads'] for r in read(C/'flow-gold.json')}
    meta={r['trace']:r for r in read(D/'corpus-audit.json')}
    families={meta[tr]['family'] for tr,z in gs.items() if z}
    assert len(families)==28
    bins=defaultdict(lambda:defaultdict(lambda:defaultdict(lambda:np.zeros(6,dtype=int))))
    masks=defaultdict(Counter);out=[]
    for rec in rg(fp):
        tr=rec['trace'];family=meta[tr]['family'];gold={z['card']:z for z in gs[tr]};allpairs=defaultdict(set)
        for z in gold.values():allpairs[z['consumer']].add(z['producer'])
        groups=['all']
        if family in families:groups.append('positive_families28')
        if family!='case/pplant':groups.append('without_pplant')
        if family in families and family!='case/pplant':groups.append('positive_families_without_pplant')
        for ev in rec['text']:
            truth=allpairs[ev['t']]
            for arm,arr in ev['arms'].items():
                y=set(arr);sample=np.array([len(truth&y),len(y-truth),len(truth-y),0,0,0])
                for which in groups:bins['text/'+which][arm][family]+=sample
        for r in rec['rows']:
            native=[gold[r[k]]['producer'] for k in ('first','next')]
            truth=[a==r['producer'] for a in native]
            cond='transition_only' if r['counts'][0]==1<r['counts'][1] else 'other_transition'
            for b in groups+[cond]:
                masks[b]['rows']+=1;masks[b]['same_native_truth']+=int(truth[0]==truth[1]);masks[b]['native_changes_producer']+=int(native[0]!=native[1]);masks[b]['prediction_bits_would_differ']+=int(cond=='transition_only')
                masks[b]['native_pattern_'+''.join('1' if j else '0' for j in truth)]+=1
            for arm,preds in r['arms'].items():
                for j,kind in [(None,'both'),(0,'historical_query'),(1,'next_read_query')]:
                    indices=range(2) if j is None else [j]
                    v=np.zeros(6,dtype=int)
                    for i in indices:
                        g,p=truth[i],preds[i];w=0 if g and p else 1 if p else 2 if g else 3;v[w]+=1
                    if j is None:v[4]=1;v[5]=int(preds==truth)
                    for b in groups+[cond]:bins[kind+'/'+b][arm][family]+=v
            out.append(dict(trace=tr,first=r['first'],next=r['next'],producer=r['producer'],truth=truth,real_producers=native,arms=r['arms'],counts=r['counts']))
    savegz(D/'time-query-outcomes.json.gz',out)
    result={}
    for k,table in bins.items():
        pairs=(('symbol_latest_operations','symbol_latest'),('symbol_latest_operations','symbol_sham_latest'),('symbol_latest','literal_latest')) if k.startswith('text/') else (('two_unique','one_early'),('two_unique','one_late'),('latest_at_query','two_unique'),('binding_privileged','latest_at_query'))
        result[k]=dict(families=len(next(iter(table.values()))),arms=diagnostics(table),comparisons={a+' minus '+b:compare(table,a,b) for a,b in pairs})
    dump(D/'followup-results.json',dict(masks=masks,panels=result))
    print('masks',masks['all'])
    for k in ('both/all','both/transition_only','text/positive_families28','text/positive_families_without_pplant'):
        print(k,{a:(z['tp'],z['fp'],z['fn'],z['both_accuracy']) for a,z in result[k]['arms'].items()})
if __name__=='__main__':{'predict':predict,'score':evaluate}[sys.argv[1]]()

