"""Secondary transfer forecast on the original physical eight-group prefix."""
from collections import defaultdict
from time import perf_counter
from common45 import *
from predict import score,weights,freeze
import numpy as np
sys.path.insert(0,str(FIX))
import forecast43 as prev
f=prev.f;api=f.api

def semantics(graph,names,qs,lookups):
    nodes={v.node_id:j for j,v in enumerate(graph.nodes)};selected=[nodes[k] for k in names]
    pool=tuple(api.pilot.native.provenance_unit_candidates(graph))
    requests=[api.ExecutionProvenanceRankingRequest(task_id=q,query_text=txt,candidates=pool,graph=graph) for q,txt in qs.items()]
    n=len(nodes);result={}
    for seed,(_,lookup) in lookups.items():
        matrix=np.empty((len(qs)*(n+1),768),dtype=np.float32)
        _,used=api.fit.features(requests,lookup,matrix,0);assert used==len(matrix)
        sim=matrix[n::n+1]@matrix[selected].T
        vec=[]
        for row in sim:
            rank=np.empty(len(names));rank[np.argsort(-row,kind='stable')]=np.arange(1,len(names)+1)
            vec.append(np.column_stack([np.log1p(rank),1/rank,(len(rank)-rank)/max(1,len(rank)-1),row]))
        result[seed]=np.vstack(vec)
    return result

def main():
    check_registration();models=weights();sdk=api.pilot
    api.torch.set_num_threads(1);api.torch.set_num_interop_threads(1);assert not api.torch.cuda.is_available()
    lookups={}
    for s in SEEDS:
        db,_=api.connect(s)
        for _,name,_ in db.execute('pragma database_list'):
            if name!='temp' and name.isidentifier():db.execute(f'pragma {name}.mmap_size=3000000000')
        lookups[s]=(db,f.native.RepeatedLookup(api.fit.Lookup(db,'ft')))
    by=defaultdict(list)
    for r in read(prev.OFF/'split.json.gz')['test']:by[r['t']].append(r['q'])
    wanted={q for qs in by.values() for q in qs}
    queries={r['id']:r['query'] for _,r in sdk.stream(sdk.Q) if r['id'] in wanted}
    tok=sdk.offsets(sdk.Tokenizer.from_file(str(sdk.CACHE/'tokenizer.json')))
    def chunk(x):return sdk.token_chunks(x,tokenizer=tok,max_tokens=504,overlap_tokens=64)
    files=[]
    for sh in range(8):
        before=perf_counter();hist=signed(FIX,f'packets-{sh}.json.gz')
        traces={v[0]:v for v in signed(FIX,f'traces-{sh}.json.gz')}
        source=api.TR/f'forecasts-main-{sh}.json.gz'
        assert sha(source)==read(api.TR/'forecast-seal.json')['forecasts'][source.name]
        index={r['q']:{v['node_id']:i for i,v in enumerate(r['rr'])} for r in read(source)}
        raw=api.RAW/f'trajectories-{sh:05d}.jsonl';assert sha(raw)==read(FIX/f'forecast-{sh}-seal.json')['source']
        rows=[];acc=defaultdict(list);p={};refs={}
        for _,origin in sdk.stream(raw):
            t=origin['session_id']
            if t not in by:continue
            prefix,groups,calls=prev.cut(iter(origin['messages']))
            assert traces[t][1:4]==[prefix is not None,groups,calls]
            if prefix is None:
                for q in by[t]:p[q]=[t,False,{}]
                continue
            tr=f.native.adapt_isetrace_record(f.native.parse_isetrace_record(prev.record(t,prefix,calls)),source_revision=sdk.RAW[1])
            tr=tr.model_copy(update={'source_metadata':None})
            graph=prev.build_provenance_graph(tr,content_chunker=chunk);assert graph.fingerprint()==traces[t][-1]
            names,_,meta,edge,_=f.auxiliary(graph,tr,len(tr.events)-1,t)
            qs={q:queries[q] for q in by[t]}
            sem=semantics(graph,names,qs,lookups)
            for s in SEEDS:acc[s].append(sem[s])
            for q in qs:
                ids=[index[q][name] for name in names]
                assert ids==hist[q][2];rows.append((q,t,len(ids),ids))
                acc['m'].append(meta);acc['e'].append(edge)
                refs[q]={str(s):dict(rich=hist[q][3][str(s)]['rich'],native=hist[q][3][str(s)]['native_wo']) for s in SEEDS}
        p.update(score(rows,np.vstack(acc['m']),np.vstack(acc['e']),{s:np.vstack(acc[s]) for s in SEEDS},models,refs))
        assert set(p)==set(hist)
        path=D/f'trigger-{sh}.json.gz';save(path,p);files.append(path)
        print('frozen',sh,len(p),'in',round(perf_counter()-before,1),'s',flush=True)
    freeze('trigger',files)
    for db,_ in lookups.values():db.close()

if __name__=='__main__':main()
