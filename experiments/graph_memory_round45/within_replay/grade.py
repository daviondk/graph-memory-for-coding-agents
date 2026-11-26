"""Join the sealed CPU rankings to spans, then check all six endpoints against the native ISETrace evaluator."""
from collections import Counter
from pathlib import Path
import sys
from forecast import D,W,R43,SEEDS,ARMS,sha,read,save,api
from graph_memory.evaluation.span_metrics import span_metrics_at,span_mrr

def strict(order,costs,budget):
    used=0;out=[]
    for i in order:
        if used+costs[i]>budget:break
        used+=costs[i];out.append(i)
    return tuple(out),used
def projection(costs,atoms,order):
    total=sum(b-a for _,a,b,_ in atoms);assert total>0
    def covered(selected):
        return sum(b-a for _,a,b,ids in atoms if selected.intersection(ids))/total
    active={i for _,a,b,ids in atoms for i in ids};rank=next((j for j,i in enumerate(order,1) if i in active),None)
    budgets=[strict(order,costs,b) for b in (512,1024,2048)]
    cov=[covered(set(selected)) for selected,_ in budgets]
    return [float(cov[2]==1),*cov,covered(set(order[:5])),1/rank if rank else 0.],budgets[-1]

def run():
    sealed=read(D/'forecast-seal.json');assert sealed['registration']==sha(D/'registration.json')
    ranks={}
    for chunk in sealed['shards']:
        f=D/chunk['file'];assert sha(f)==chunk['sha']
        part=read(f);assert not ranks.keys()&part.keys();ranks.update(part)
    assert len(ranks)==2000
    reg=read(D/'registration.json')['pairs']
    records={s:read(R43/f'paired-{s}.json.gz') for s in SEEDS}
    label_path=W/'graph_memory_round18/isetrace_official/gold-spans.json.gz'
    atom_path=W/'graph_memory_round34/interval_witness/test-atoms.json.gz'
    labels=read(label_path);atoms=read(atom_path)
    out={};qa=Counter()
    for sh in range(8):
        for row in read(W/f'graph_memory_round19/trained_rank/forecasts-main-{sh}.json.gz'):
            q,t=row['q'],row['t'];old_t,orders=ranks.pop(q);assert old_t==t and len(orders)==15
            nodes=tuple(api.pilot.RankedNodeRecord.model_validate(n) for n in row['rr']);costs=[n.token_count for n in nodes]
            gold=tuple(api.pilot.SourceSpan.model_validate(s) for s in labels[q])
            cache={}
            def measure(key):
                order=tuple(orders[key])
                if order not in cache:
                    assert sorted(order)==list(range(len(nodes)))
                    values,(packet,cost)=projection(costs,atoms[q],order)
                    native_nodes=tuple(nodes[i] for i in order)
                    br=[api.pilot.span_metrics_under_token_budget(native_nodes,gold,b) for b in (512,1024,2048)]
                    native=[float(br[2].full_support),*[v.coverage for v in br],span_metrics_at(native_nodes,gold,5).coverage,span_mrr(native_nodes,gold)]
                    assert max(abs(a-b) for a,b in zip(values,native))<1e-12
                    cache[order]=[values,cost]
                return cache[order]
            scores={}
            for s in SEEDS:
                arms={};gpu=records[s][q];assert gpu[0]==t
                for aidx,a in enumerate(ARMS):
                    conf=reg[f'{s}-{a}']
                    recall,matched=[measure(f"{s}/{a}/{conf[choice]}") for choice in ('recall','budget')]
                    if conf['recall']==conf['budget']:assert matched==recall
                    gpu_budget=gpu[5+aidx];gpu_canonical=gpu[3+aidx]
                    arms[a]={'recall':recall,'matched':matched,'gpu_matched':gpu_budget,'gpu_canonical':gpu_canonical}
                    qa['cpu_gpu_full_support_matches']+=int(matched[0][0]==gpu_budget[0])
                    qa['cpu_gpu_six_metric_matches']+=int(all(abs(x-y)<1e-12 for x,y in zip(matched[0],gpu_budget)))
                scores[str(s)]=arms
            qa['native_order_evaluations']+=len(cache);out[q]=[t,scores]
    assert len(out)==2000 and len(set(v[0] for v in out.values()))==1207 and not ranks
    save(D/'scores.json.gz',out);save(D/'grade-seal.json',{'forecasts':sha(D/'forecast-seal.json'),'scores':sha(D/'scores.json.gz'),'gold':sha(label_path),'atoms':sha(atom_path),'cpu_gpu_n':20000,'qa':dict(qa)})
if __name__=='__main__':run()

