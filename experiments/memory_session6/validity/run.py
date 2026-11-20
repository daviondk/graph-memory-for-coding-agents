"""Seal per-query choices without access to the current search result."""
import gzip,json,hashlib,time
from pathlib import Path
from prepare import ROOT,emit
from policy import Writer,METHODS,vi
def source(p):
    with gzip.open(p,'rt',encoding='utf8') as f:
        for l in f:yield json.loads(l)
def main():
    costs=[];start=time.perf_counter();dec=ROOT/'decisions.jsonl.gz'
    with gzip.open(dec,'wt',encoding='utf8',compresslevel=3) as stream:
        for p in sorted((ROOT/'projection').glob('*.gz')):
            nf=ROOT/'natural'/(p.name.split('.')[0]+'_inputs.gz')
            extra={r['step']:r['queries'] for r in source(nf)} if nf.exists() else {}
            for r in source(p):
                fs=r['files'];states=r['queries']+extra.get(r['step'],[]);lookup={f['p']:i for i,f in enumerate(fs)}
                for budget in (128,512,2048):
                    writer=Writer(fs,budget);canonical={};wire=bytearray();changes=0
                    enrolled={q['t']:q for q in states}
                    for qi,(t,q) in enumerate(sorted(enrolled.items())):
                        changed=[]
                        for fi,f in enumerate(fs):
                            old=q['prior'].get(f['p'],0);new=old+f['net'].get(t,0)
                            assert new>=0
                            if bool(old)!=bool(new):changed.append((fi,new>0))
                        canonical[t]=changed
                        if changed:
                            wire.extend(vi(qi)+vi(len(changed)))
                            for fi,plus in changed:wire.extend(vi(2*fi+int(plus)))
                            changes+=1
                    cost={'repo':r['repo'],'step':r['step'],'budget':budget,'paths':len(fs),'path_registry_bytes':sum(len(f['p'].encode())+1 for f in fs),'patch_bytes':r['patch_bytes'],'line_bytes':r['edited_line_bytes'],'whole_old_new_bytes':sum(f['old_bytes']+f['new_bytes'] for f in fs),
                          'exact_compressed':writer.exact_cost,'subscription_note_count':len(enrolled),'subscription_enrollment_key_bytes':sum(q['length']+1 for q in enrolled.values()),'prior_count_extra_varint_bytes':sum(len(vi(v)) for q in enrolled.values() for v in q['prior'].values()),'subscription_bitmap_bytes':(len(enrolled)+7)//8,'subscription_patch_bytes':1+len(wire),'changed_registered':changes}
                    costs.append(cost)
                    for i,q in enumerate(states):
                        decisions={a:[lookup[p] for p in (writer.live if canonical[q['t']] else [])] if a=='subscriptions' else [lookup[p] for p in writer.reads(a,q)] for a in METHODS}
                        stream.write(emit({'repo':r['repo'],'step':r['step'],'arm':q['arm'],'t':q['t'],'budget':budget,'read':decisions})+'\n')
    (ROOT/'wire_costs.json.gz').write_bytes(gzip.compress(emit(costs).encode(),mtime=0))
    (ROOT/'decision_lock.json').write_text(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (ROOT/'policy.py',ROOT/'run.py',ROOT/'PROTOCOL.md',ROOT/'MECHANISMS.md',dec,ROOT/'wire_costs.json.gz')},indent=1));print('commits',len(costs)//3,'seconds',round(time.perf_counter()-start,1))
if __name__=='__main__':main()
