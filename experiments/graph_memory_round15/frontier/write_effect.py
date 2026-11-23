"""Post-outcome mechanistic decompositions; do not alter frozen predictions."""
from frontier import *
from score import K,ENDS
import statistics

def main():
    forecasts=read(D/'forecasts.json.gz');inputs=read(D/'frontier_inputs.json.gz');outs=read(D/'outcomes.json.gz');res={}
    for panel,L in inputs.items():
        points=collections.defaultdict(list)
        for r,p,t in zip(L,forecasts[panel],outs[panel]):
            assert r['id']==p['id']==t['id']
            old=set(r['viewed']);typed=p['ranks']['typed_union'];project=[a for a in typed if a in old]
            row={**r,'docs':r['viewed']}
            # Scalar statistics recomputed on exactly the old menu.
            rerank=predict(row,{'front':{}})[0]['flat_union']
            for ep in ENDS:
                goal=set(t[ep])
                if not goal:continue
                rw={'id':r['id'],'iid':r['iid'],'new_gold_sources':sorted(set(typ for z in goal&set(r['frontier']) for typ in r['frontier'][z]['sources'])),
                    'old_oracle':bool(goal&old),'front_oracle':bool(goal&set(r['frontier']))}
                for k in K:
                    rw[str(k)]={'all':bool(goal&set(typed[:k])),'projected':bool(goal&set(project[:k])),'reranked':bool(goal&set(rerank[:k]))}
                points[ep].append(rw)
        res[panel]={}
        for ep,vs in points.items():
            dst={};c=collections.Counter(src for d in vs if not d['old_oracle'] for src in d['new_gold_sources'])
            for k in K:
                k=str(k);data=[v[k] for v in vs];m={t:sum(v[t] for v in data) for t in ('all','projected','reranked')}
                for comp in ('projected','reranked'):
                    m['gain_vs_'+comp]=sum(v['all'] and not v[comp] for v in data)
                    m['loss_vs_'+comp]=sum(not v['all'] and v[comp] for v in data)
                dst[k]=m
            res[panel][ep]={'n':len(vs),'results_at_k':dst,'new_only_source_presence':c}
    save('write_effect.json',res)
if __name__=='__main__':main()
