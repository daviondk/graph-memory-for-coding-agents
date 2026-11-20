import base64,math,statistics
from collections import Counter,defaultdict
import numpy as np
from util12 import D,load,dump,sha
from dictionary import decode
from write import BS,SEEDS
from store12 import ARMS
FIELDS=['emit','diff','p64','p4k','replay','append','changed','cow','active_g','inactive_g','compressed_excess','nondirty','exactsize','missed','fp','tn_all','hit','stale','stale_possible','chg_fp','chg_tn','chg_miss','away_fp','away_tn','compact','updates','unchanged_index','peak_actual']
def tally(vals,mask,oldmask,subset,absent,n):
    full=(1<<n)-1;out=Counter()
    for w,pred in vals.items():
        actual=mask.get(w,0);wrong=pred&~actual&full;drop=actual&~pred&full;negative=(~actual)&full;hist=oldmask.get(w,0)&negative
        out.update(missed=drop.bit_count(),fp=wrong.bit_count(),tn_all=negative.bit_count(),hit=(actual&pred).bit_count(),stale=(wrong&hist).bit_count(),stale_possible=hist.bit_count())
        if w in subset:out.update(chg_fp=wrong.bit_count(),chg_tn=negative.bit_count(),chg_miss=drop.bit_count())
        if w in absent:out.update(away_fp=wrong.bit_count(),away_tn=negative.bit_count())
    assert not out['missed']
    return out
def label(x):return str(x[0])+'/'+str(x[1])+'/'+str(x[2])+'/'+x[3]
def main():
    for f in ['read_seal.json','exact_seal.json']:
        for p,h in load(D/f).items():assert sha(D/p)==h
    cells=defaultdict(Counter);perstep=[];snaprecord=[]
    for p in sorted((D/'events').glob('*.gz')):
        e=load(p);t=e['task'];n=e['n'];allw=set();seen={};current={};truth={};gauge=[]
        for row in e['events']:
            i=row['i'];words=set(row['words']);prior=current.get(i,set());gauge.append(len(prior^words));current[i]=words
            for w in words:seen[w]=seen.get(w,0)|1<<i
            bykey={}
            for j,vals in current.items():
                for w in vals:bykey[w]=bykey.get(w,0)|1<<j
            truth[row['step']]=(dict(bykey),dict(seen))
        pred=load(D/'predictions'/p.name);qs=pred['keys'];qinfo=load(D/'probes'/p.name);subset=set(qinfo['changed_definitions']);away=set(qinfo['guaranteed_absent'])
        def update(step,phase,b,s,gate,arm,vals,x):
            mask,past=truth[step];score=tally(dict(zip(qs,vals)),mask,past,subset,away,n)
            score.update(x);score.update(updates=1,changed=gauge[step]);cells[t,phase,b,s,gate,arm].update(score)
            perstep.append([t,step,phase,b,s,gate,arm,dict(score)])
        for rr,st in zip(pred['rows'],load(D/'states'/p.name)['rows']):
            step,phase,b,s,gate,arm,encoded=rr;assert rr[:6]==st[:6]
            x=st[-1];raw=base64.b64decode(st[6]);vals=base64.b64decode(encoded)
            fail=0
            if arm=='exact_dict':fail=int(raw[8]==255)
            if arm=='exact_forward':
                from store12 import layout
                fail=int(any(raw[a]==255 for a,c in layout(arm,len(raw),n)))
            update(step,phase,b,s,gate,arm,vals,dict(emit=x['emitted'],diff=x['byte_changes'],p64=x['pages64'],p4k=x['pages4096'],replay=x['replay_bytes'],append=x['arch_append'],cow=x['cow_index_peak'],peak_actual=len(raw),compressed_excess=fail,compact=x['compact'],unchanged_index=x['noop']))
        for step,phase,b,gate,enc,reads,st in load(D/'exact_states'/p.name):
            raw=base64.b64decode(enc);mp=decode(raw);vals=[raw[2] if mp is None else mp.get(q,0) for q in qs]
            arm='mutable_exact' if b else 'uncapped_exact'
            for s in SEEDS:
                update(step,phase,b,s,gate,arm,vals,dict(emit=st['emitted'],diff=st['byte_changes'],p64=st['pages64'],p4k=st['pages4096'],replay=st['replay'],append=e['events'][step]['archive_bytes'],cow=st['cow'],peak_actual=len(raw),compressed_excess=int(not st['fit']),compact=bool(st['emitted']),unchanged_index=not st['emitted']))
            if b==0 and gate==0:snaprecord.append(dict(t=t,step=step,phase=phase,exact=len(raw),n=n))
    mods=sorted({k[0] for k in cells}); boot=np.random.default_rng(12041).integers(0,len(mods),(10000,len(mods)))
    stats={};effects={}
    def cell(t,phase,b,g,a):
        merged=sum((cells[t,phase,b,s,g,a] for s in SEEDS),Counter())
        merged={k:v/len(SEEDS) for k,v in merged.items()};return merged
    def metric(v,key):
        if key=='fp':return v.get('fp',0)/v['tn_all']
        if key=='changed_fp':return v.get('chg_fp',0)/max(1,v.get('chg_tn',0))
        if key=='stale':return v.get('stale',0)/max(1,v.get('stale_possible',0))
        if key=='away_fp':return v.get('away_fp',0)/v['away_tn']
        if key=='write_plus_replay':return (v.get('emit',0)+v.get('replay',0))/v['updates']
        return v.get(key,0)/v['updates']
    for phase in [0,1]:
        for b in BS+[0]:
            arms=ARMS+['mutable_exact'] if b else ['uncapped_exact']
            for g in [0,1]:
                for a in arms:
                    ms=[cell(t,phase,b,g,a) for t in mods];pooled=Counter()
                    for m in ms:pooled.update(m)
                    stats[label([phase,b,g,a])]=dict(pooled={k:metric(pooled,k) for k in ['fp','changed_fp','stale','away_fp','emit','diff','p64','p4k','replay','write_plus_replay','cow','append','peak_actual','compressed_excess','compact','unchanged_index']},counts=pooled,modules={t:m for t,m in zip(mods,ms)})
                    if not b:continue
                    for ref in ['global_xor','column_bloom','edge_delta','mutable_exact']:
                        if a==ref:continue
                        for metricname in ['fp','emit','write_plus_replay']:
                            dif=np.array([metric(m,metricname)-metric(cell(t,phase,b,g,ref),metricname) for t,m in zip(mods,ms)]);vs=dif[boot].mean(1);w=sum(dif< -1e-12);l=sum(dif>1e-12);nk=int(w+l)
                            pv=min(1.,2*sum(math.comb(nk,i) for i in range(min(w,l)+1))/2**nk) if nk else 1
                            effects[label([phase,b,g,a])+'-'+ref+'-'+metricname]=dict(delta=float(dif.mean()),lo=float(np.quantile(vs,.025)),hi=float(np.quantile(vs,.975)),lower=int(w),equal=len(dif)-nk,higher=int(l),sign_p=pv)
    dump(D/'graded_rows.json.gz',perstep);dump(D/'results.json',dict(cells=stats,effects=effects,uncapped_sizes=snaprecord,modules=mods))
    for b in BS:
        print('cap',b)
        for a in ARMS+['mutable_exact']:
            v=stats[label([1,b,0,a])]['pooled'];print(a,*[round(v[k],3) for k in ['emit','replay','fp','changed_fp','p4k','compressed_excess']])
if __name__=='__main__':main()