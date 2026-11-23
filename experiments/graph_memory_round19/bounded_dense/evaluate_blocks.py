"""Join spans only after all bounded-reader predictions have been sealed."""
from collections import defaultdict
from statistics import mean
import sys
from inputs import ROOT,RUN,ARMS,TR,DE,load,put,pilot
from evaluate import compare
from verify_records import metrics
from graph_memory.evaluation.span_metrics import span_metrics_at
from graph_memory.retrieval.results import RankedNodeRecord
from graph_memory.trajectories import SourceSpan
def run():
    seal=load(ROOT/'forecast-seal.json');assert all(pilot.sha(ROOT/f)==h for f,h in seal['forecasts'].items());assert seal['plan']==pilot.sha(ROOT/'reader-plan.json')
    oldall=load(ROOT.parent/'write_learned/transfer-outcomes.json.gz');prev={(r['split'],r['q']):r['a'] for r in oldall}
    stored=[];out=[];summary={};comp={}
    for stage in ('test','dev'):
        gp=TR.parents[1]/'graph_memory_round18/isetrace_official/gold-spans.json.gz' if stage=='test' else DE/'gold-spans.json.gz'
        truth=load(gp);items=defaultdict(dict);spent=defaultdict(list)
        for i in range(8):
            for r in load(ROOT/f'forecasts-{stage}-{i}.json.gz'):
                src={int(j):m for j,m in r['b'].items()}
                nd={j:RankedNodeRecord(node_id=str(j),score=0.,token_count=c,source_spans=(SourceSpan(event_id=e,json_pointer=ptr,char_start=lo,char_end=hi),)) for j,(e,ptr,lo,hi,c,nb) in src.items()}
                for a in ARMS:
                    keep=r['arms'][a]['k'];S=[nd[j] for j in keep];event={(src[j][0],src[j][1]) for j in keep};pay=sum(src[j][5] for j in keep)
                    wire=pay+28*len(keep)+sum(12+len(e.encode())+len(p.encode()) for e,p in event)
                    storage=dict(split=stage,t=r['t'],arm=a,stored_tokens=sum(n.token_count for n in S),count=len(S),utf8_bytes=pay,
                               text_wire_bytes=wire,fp32_vector_bytes=3072*len(S),writer_model_bytes=3911 if a=='full' else 0)
                    assert storage['stored_tokens']<=8192
                    stored.append(storage);spent[a].append(storage)
                    for q,methods in r['arms'][a]['per'].items():
                        gold=tuple(SourceSpan.model_validate(s) for s in truth[q]);written=span_metrics_at(tuple(S),gold,len(S))
                        assert int(written.full_support)==prev[stage,q]['tokens/'+a][0]
                        for method,chosen in methods.items():
                            assert set(chosen)<=set(keep) and len(chosen)==len(set(chosen))
                            selected=tuple(nd[j] for j in chosen);cost=sum(n.token_count for n in selected);assert cost<=2048
                            v=pilot.span_metrics_under_token_budget(selected,gold,2048)
                            ind=metrics(truth[q],[n.model_dump() for n in selected]);assert all(abs(z-getattr(v,k))<1e-12 for k,z in zip(('coverage','density','full_support'),ind,strict=True))
                            if method=='bm25':
                                old=prev[stage,q]['tokens/'+a];assert all(abs(x-y)<1e-12 for x,y in zip((v.full_support,v.coverage,v.density,cost),old[3:7],strict=True))
                            rec=dict(q=q,t=r['t'],stage=stage,writer=a,reader=method,tokens=cost,nodes=len(chosen),full_support=v.full_support,coverage=v.coverage,density=v.density,f1=v.f1,
                                     write_fs=written.full_support,write_coverage=written.coverage)
                            out.append(rec);assert q not in items[a+'/'+method];items[a+'/'+method][q]=rec
        assert all(set(rs)==set(truth) for rs in items.values())
        meas={k:{m:mean(v[m] for v in rs.values()) for m in ('full_support','coverage','density','f1','tokens','nodes','write_fs','write_coverage')}|dict(n=len(rs),hits=int(sum(v['full_support'] for v in rs.values()))) for k,rs in items.items()}
        money={a:{k:mean(v[k] for v in ss) for k in ('stored_tokens','count','utf8_bytes','text_wire_bytes','fp32_vector_bytes','writer_model_bytes')} for a,ss in spent.items()}
        comparisons={}
        for method in ('dense','bm25','rrf60'):
            for b in ('output_head','fifo'):
                k='full/'+method+'-'+b+'/'+method;comparisons[k]=compare(items['full/'+method],items[b+'/'+method])
        for a in ARMS:
            for meth in ['dense','rrf60']:comparisons[a+'/'+meth+'-'+a+'/bm25']=compare(items[a+'/'+meth],items[a+'/bm25'])
        summary[stage]=dict(metrics=meas,storage=money,contrasts=comparisons,n=len(truth),trajectories=len({v['t'] for v in items['full/dense'].values()}),gold_sha256=pilot.sha(gp))
    put(ROOT/'outcomes.json.gz',out);put(ROOT/'storage.json.gz',stored);put(ROOT/'results.json',summary)
    print({s:{a:x['hits'] for a,x in v['metrics'].items()} for s,v in summary.items()})
if __name__=='__main__':run()
