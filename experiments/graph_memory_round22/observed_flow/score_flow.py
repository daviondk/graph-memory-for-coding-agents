"""Evaluate sealed forecasts, including statement actions without any eligible read."""
from collections import Counter,defaultdict
from pathlib import Path
import gzip
import json
import numpy as np
from sources import D,C,read,dump,sha


def rates(v):
    tp,fp,fn=map(int,v)
    return dict(tp=tp,fp=fp,fn=fn,precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,f1=(2*tp/(2*tp+fp+fn)) if 2*tp+fp+fn else None)


def diffs(a,b):
    fam=sorted(set(a)|set(b))
    ax=np.array([a.get(k,np.zeros(3)) for k in fam]);bx=np.array([b.get(k,np.zeros(3)) for k in fam])
    def metric(v):
        tp,fp,fn=np.moveaxis(v,-1,0)
        return np.stack([np.divide(tp,tp+fp,out=np.full(tp.shape,np.nan),where=tp+fp>0),np.divide(tp,tp+fn,out=np.full(tp.shape,np.nan),where=tp+fn>0),np.divide(2*tp,2*tp+fp+fn,out=np.full(tp.shape,np.nan),where=2*tp+fp+fn>0)],axis=-1)
    sample=np.random.default_rng(2209).integers(0,len(fam),size=(5000,len(fam)))
    delta=metric(ax[sample].sum(axis=1))-metric(bx[sample].sum(axis=1))
    point=metric(ax.sum(axis=0))-metric(bx.sum(axis=0));ret={}
    for j,m in enumerate(['precision','recall','f1']):
        finite=delta[:,j][np.isfinite(delta[:,j])]
        ret[m]=dict(delta_pp=round(100*point[j],6) if np.isfinite(point[j]) else None,ci95_pp=(100*np.quantile(finite,[.025,.975])).tolist() if len(finite) else None,finite_replicates=len(finite))
    return ret


def main():
    pred=read(D/'prediction-lock.json');inputs=read(D/'input-lock.json')
    assert sha((D/'predictions.json.gz').read_bytes())==pred['predictions'] and sha((C/'flow-gold.json').read_bytes())==inputs['gold']
    assert sha((D/'predict_flow.py').read_bytes())==pred['selector'] and sha((D/'protocol.json').read_bytes())==pred['protocol']
    forecasts=json.loads(gzip.decompress((D/'predictions.json.gz').read_bytes()))
    gold={r['trace']:r['reads'] for r in read(C/'flow-gold.json')}
    audit={r['trace']:r for r in read(D/'corpus-audit.json')}
    cells=defaultdict(lambda:defaultdict(lambda:defaultdict(lambda:np.zeros(3,dtype=int))))
    denominators=Counter();cases=[];unit_counts=defaultdict(Counter)
    def enter(sets,kind,context,family,arms,truth,extra):
        recs={}
        for label,values in arms.items():
            picks=set(values);a=np.array([len(picks & truth),len(picks-truth),len(truth-picks)],dtype=int)
            for sg in sets:cells[kind+'/'+sg][label][family]+=a
            recs[label]=a.tolist()
        for sg in sets:denominators[kind+'/'+sg]+=1
        cases.append(dict(**context,kind=kind,outcomes=recs,**extra))
    for r in forecasts:
        tr=r['trace'];info=audit[tr];fam=info['family'];groups=['all',info['repo'],'regression' if info['repo'] in ('rdtLite','RDataTracker') else 'other_examples']
        native={z['card']:z for z in gold[tr]};pairs=defaultdict(set)
        for z in native.values():pairs[z['consumer']].add(z['producer'])
        assert set(native)=={c['id'] for c in r['cards']}
        for c in r['cards']:
            z=native[c['id']];g=z['producer'];s=c['arms']
            assert z['consumer']==c['t'] and g in s['universal'] # read-value and generator visibility supplied by the design
            typ='ambiguous_at_read' if c['before']>1 else 'future_collision_only' if c['final']>1 else 'always_unique'
            enter(groups+[typ],'card',dict(trace=tr,card=c['id'],t=c['t']),fam,s|{'version_oracle':[g]},{g},dict(collision=typ,reference_source=g))
        for e in r['text']:
            truth=pairs[e['t']]
            enter(groups+(['positive_action'] if truth else ['no_eligible_read']),'text',dict(trace=tr,t=e['t']),fam,e['arms'],truth,dict(reference_sources=sorted(truth)))
    summary={};comparisons={'card':[('retract','append'),('latest','append'),('latest','random_value'),('universal','latest'),('latest_binding_or_name','latest'),('append','sham_append')],'text':[('literal_retract','literal_append'),('literal_latest','literal_universal'),('symbol_retract','symbol_append'),('symbol_latest','symbol_universal'),('symbol_latest','symbol_sham_latest')]}
    for key,methods in sorted(cells.items()):
        kind=key.split('/')[0];summary[key]=dict(n=denominators[key],families=len(next(iter(methods.values()))),arms={})
        for name,groups in methods.items():
            vals=np.array(list(groups.values()))
            result=rates(vals.sum(axis=0))
            mac=[rates(v)['f1'] for v in vals]
            result['mean_family_f1']=float(np.mean([v for v in mac if v is not None])) if any(v is not None for v in mac) else None
            result['families_defined_f1']=sum(v is not None for v in mac)
            summary[key]['arms'][name]=result
        summary[key]['comparisons']={f'{a} minus {b}':diffs(methods[a],methods[b]) for a,b in comparisons[kind]}
    pp=D/'outcomes.json.gz';pp.write_bytes(gzip.compress((json.dumps(cases,sort_keys=True,separators=(',',':'))+'\n').encode(),mtime=0))
    dump(D/'results.json',summary)
    dump(D/'evaluation-lock.json',dict(outcomes=sha(pp.read_bytes()),results=sha((D/'results.json').read_bytes()),forecast=pred['predictions'],score=sha(Path(__file__).read_bytes())))
    for k in ('card/all','card/ambiguous_at_read','card/future_collision_only','card/always_unique','text/all'):
        print(k,summary[k]['n'],{m: (x['tp'],x['fp'],x['fn']) for m,x in summary[k]['arms'].items() if m in ('universal','append','retract','latest','latest_binding_or_name','literal_retract','literal_append','literal_universal','symbol_retract','symbol_append','symbol_latest','symbol_universal')})
if __name__=='__main__':main()

