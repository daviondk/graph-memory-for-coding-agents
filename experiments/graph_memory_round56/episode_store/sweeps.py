"""Physical test and independent member-level audit of the pointer-free union of suffixes."""
import argparse
from collections import defaultdict
from pathlib import Path
import random
import shutil
from statistics import median
import tempfile
from time import perf_counter_ns
from bench import HERE,PANELS,SEED,connect,execute,io,project
from extra_store import evidence as extra_evidence
from store import initialize,update,evidence
from sweep_store import MODES,materialized,witnesses

PLANS=('inline','packed8',*MODES)

def main(scratch):
    corp={k:{repo:project(s) for repo,s in io(p/'commits.json.gz').items()} for k,p in PANELS.items()}
    rng=random.Random(SEED+3)
    blocks=[]
    for block in range(5):
        schedule=[(k,repo,m) for k,repos in corp.items() for repo in repos for m in PLANS]
        rng.shuffle(schedule)
        data=[]
        with tempfile.TemporaryDirectory(dir=scratch,prefix='r56-suffix-sweep-') as folder:
            path=Path(folder)/'active.sqlite'
            for k,repo,m in schedule:
                rows,oracle=corp[k][repo]
                results,metrics=execute(path,repo,rows,oracle,m,0,block,False)
                assert all(results[t]==g['recent'] for t,g in oracle.items())
                targets=list(dict.fromkeys(q[0] for _,_,_,q in reversed(rows) if q and q[0]>=0))[:20]
                first=warm=0
                for a in targets:
                    db=connect(path)
                    now=perf_counter_ns()
                    cold=evidence(db,m,a)
                    mid=perf_counter_ns()
                    again=evidence(db,m,a)
                    end=perf_counter_ns()
                    assert again==cold
                    first+=mid-now
                    warm+=end-mid
                    db.close()
                metrics['evidence_ns']=[first,warm,len(targets)]
                if block==0 and repo=='pallets/flask' and m=='blocksweep':
                    shutil.copyfile(path,HERE/'example-flask-blocks.sqlite')
                path.unlink()
                data.append([k,repo,m,metrics])
        blocks.append(data)
        print('sweep',block+1,len(data),flush=True)
    io(HERE/'sweep-measurements.json.gz',blocks)
    return blocks

def independent():
    counts=defaultdict(int)
    unions={}
    for panel,p in PANELS.items():
        for repo,s in io(p/'commits.json.gz').items():
            rows,_=project(s)
            for m in MODES:
                db=connect(':memory:')
                initialize(db,m)
                owners=defaultdict(list)
                full={}
                live_after_last_sweep=set()
                for t,(_,nodes,born,q) in enumerate(rows):
                    if q:
                        assert witnesses(db,m,q[0])==list(reversed(owners[q[0]][-8:]))
                        counts['preupdate_source_answers']+=1
                    update(db,m,0,t,nodes,born)
                    if nodes:
                        full[t]=nodes
                        live_after_last_sweep.add(t)
                    for a in nodes:owners[a].append((t,nodes))
                    if (t+1)%32==0 or t==len(rows)-1:
                        closure={u for hist in owners.values() for u,_ in hist[-8:]}
                        if (t+1)%32==0:live_after_last_sweep=set(closure)
                        expect=live_after_last_sweep if m in ('blocksweep','sweepscan') else set(full)
                        retained=materialized(db,m)
                        assert set(retained)==expect and all(full[i]==v for i,v in retained.items())
                        counts['retained_event_identity_comparisons']+=len(expect)
                        # Every known anchor must retain exact source ordinals and full member sets.
                        for a,seq in owners.items():
                            assert witnesses(db,m,a)==list(reversed(seq[-8:]))
                            counts['all_anchor_checkpoint_source_answers']+=1
                unions[repo]=dict(ever_events=len(full),last_live=len(closure),swept_plus_tail=len(live_after_last_sweep),
                                  eight_owner_pointers=sum(min(8,len(seq)) for seq in owners.values()),files=len(owners))
                db.close()
    return dict(counts=counts,unions=unions)

def summarize(records):
    result={}
    for panel in PANELS:
        table={}
        for m in PLANS:
            samples=[]
            for block in records:
                rows=[r for k,repo,met,r in block if k==panel and met==m]
                assert len(rows)==6
                sample={z:sum(r[z] for r in rows) for z in ('compact_bytes','file_bytes','changed_rows','query_ns','update_ns')}
                for field in ('evidence_ns','first_warm_ns'):
                    fieldrows=[r[field] for r in rows]
                    n=sum(v[-1] for v in fieldrows)
                    sample[field+'_cold_us']=sum(v[-3] for v in fieldrows)/n/1000
                    sample[field+'_warm_us']=sum(v[-2] for v in fieldrows)/n/1000
                samples.append(sample)
            table[m]={z:median(s[z] for s in samples) for z in samples[0]}
        result[panel]=table
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('mode',choices=['bench','audit','verify'])
    ap.add_argument('--scratch',type=Path,default=Path('D:/CodexResearch'))
    args=ap.parse_args()
    if args.mode=='bench':
        data=summarize(main(args.scratch))
        io(HERE/'sweep-results.json',data)
        for k,p in data.items():
            print(k,[(m,r['compact_bytes'],round(r['query_ns']/1e6,1),round(r['evidence_ns_warm_us'],1)) for m,r in p.items()])
    elif args.mode=='audit':
        val=independent();io(HERE/'sweep-audit.json',val);print(val['counts'])
    else:
        assert summarize(io(HERE/'sweep-measurements.json.gz'))==io(HERE/'sweep-results.json')
        assert independent()==io(HERE/'sweep-audit.json')
