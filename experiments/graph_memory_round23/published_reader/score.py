"""Score already sealed source intervals and recompute each physical-token receipt."""
from inputs import *
from collections import Counter
from statistics import mean
from scipy.stats import binomtest
from tokenizers import Tokenizer

def union(spans):
    out=[]
    for a,b in sorted(map(tuple,spans)):
        if out and a<=out[-1][1]:
            out[-1][1]=max(b,out[-1][1])
        else:out.append([a,b])
    return out
def groups(items):
    by=defaultdict(list)
    for addr,a,b in items:by[tuple(addr)].append((a,b))
    return {addr:union(r) for addr,r in by.items()}
def length(d):
    return sum(b-a for spans in d.values() for a,b in spans)
def measure(items,truth):
    pred=groups(items);den=length(pred);total=length(truth)
    overlap=sum(max(0,min(b,v)-max(a,u)) for e,ss in pred.items() for a,b in ss for u,v in truth.get(e,[]))
    assert 0<=overlap<=total and overlap<=den and total>0
    cov=overlap/total;density=overlap/den if den else 0.0
    return {'full':int(total==overlap),'coverage':cov,'density':density,
            'f1':2*cov*density/(cov+density) if cov+density else 0.,'chars':den}
def compare(rows,left,right):
    keys=('full','coverage','density','f1','tokens')
    arr=np.array([[r['scores'][left][k]-r['scores'][right][k] for k in keys] for r in rows])
    rng=np.random.default_rng(13);samples=[]
    for _ in range(100):
        index=rng.integers(0,len(rows),size=(100,len(rows)));samples.append(arr[index].mean(axis=1))
    lo,hi=np.quantile(np.vstack(samples),[.025,.975],axis=0)
    win=int((arr[:,0]>0).sum());loss=int((arr[:,0]<0).sum())
    return {'diff':{k:{'estimate':float(est),'ci95':[float(l),float(h)]} for k,est,l,h in zip(keys,arr.mean(axis=0),lo,hi,strict=True)},
            'wins':win,'losses':loss,'ties':len(rows)-win-loss,'mcnemar_two_sided':float(binomtest(win,win+loss,.5).pvalue) if win+loss else 1.}
def score(stage):
    seal=load(HERE/f'{stage}-seal.json');inputs=load(HERE/f'{stage}-inputs.json');assert sha(HERE/f'{stage}-inputs.json')==seal['inputs']
    for q,chk in seal['files'].items():assert sha(HERE/'forecasts'/stage/f'{q[6:]}.json.gz')==chk
    gold_path=R19/'write_transfer/gold-spans.json.gz' if stage=='dev' else WORK/'graph_memory_round18/isetrace_official/gold-spans.json.gz'
    gold=load(gold_path);tok=Tokenizer.from_file(str(E5));assert tok.truncation is None
    rows=[];lengths=[];windows=[];counts=[[],[]];longest=0;pooled=[]
    for q,chk in sorted(seal['files'].items()):
        r=load(HERE/'forecasts'/stage/f'{q[6:]}.json.gz');private=PRIVATE/stage/f'{q[6:]}.json.gz';s=load(private)
        assert r['q']==q and r['input']==sha(private) and r['ad']==s['ad'] and r['code']==seal['code'] and s['q']==q
        truth=groups([( (v['event_id'],v['json_pointer']),v['char_start'],v['char_end']) for v in gold[q]])
        def source(items):return [(r['ad'][e],a,b) for e,a,b in items]
        oracle=measure(source(r['parent_spans']),truth);pooled.append(oracle)
        scores={}
        for arm,pick in r['picks'].items():
            intervals=pick['spans'];ctx='\n'.join(s['fields'][str(e)][a:b] for e,a,b in intervals)
            assert h(ctx.encode())==pick['context_sha']
            cost=len(tok.encode(ctx,add_special_tokens=False).ids);assert cost==pick['tokens']<=2048
            for e,a,b in intervals:assert any(y==e and l<=a<b<=z for y,l,z in r['parent_spans'])
            m=measure(source(intervals),truth);assert m['coverage']<=oracle['coverage']+1e-12
            assert sum(b-a for _,a,b in intervals)==m['chars']
            scores[arm]={**m,'tokens':cost,'empty':int(not intervals),'under_half':int(cost<1024)}
        lengths.extend(v[1] for v in r['inferences']);windows.extend(v[2] for v in r['inferences']);longest=max(max(lengths),longest)
        for k in (0,1):counts[k].extend(v[3+k][0] for v in r['inferences'])
        rows.append({'q':q,'t':r['t'],'oracle':oracle,'scores':scores,'parents':len(r['inferences']),'sec_default':r['elapsed_default'],'sec_recall':r['elapsed_recall']})
    assert len(rows)==len({r['t'] for r in rows})==seal['n']
    arms=rows[0]['scores'].keys();summary={a:{k:mean(r['scores'][a][k] for r in rows) for k in rows[0]['scores'][a]} for a in arms}
    diffs={f'{left}-{right}':compare(rows,left,right) for left,right in [('fine','verbatim_core'),('fine','whole'),('fine','parent'),('verbatim_core','verbatim'),('verbatim_fill','verbatim_core'),('verbatim_recall_core','verbatim_core'),('verbatim_fill','fine')]}
    save(HERE/f'{stage}-outcomes.json.gz',rows)
    summary_file={'n':len(rows),'measures':summary,'contrasts':diffs,'oracle':{k:mean(row[k] for row in pooled) for k in ('full','coverage')},
                  'nodes':len(lengths),'published_window_tokens':8192,'longest_pair':longest,'sliding_windows':max(windows),'nodes_with_multiple_windows':sum(w>1 for w in windows),
                  'published_nonempty_nodes':[sum(n>0 for n in vals) for vals in counts],'query_seconds_default':{quant:float(np.quantile([r['sec_default'] for r in rows],p)) for quant,p in [('p50',.5),('p95',.95)]},
                  'cluster_unit':'one query per trajectory','bootstrap':10000,'seal':sha(HERE/f'{stage}-seal.json'),'per_query':sha(HERE/f'{stage}-outcomes.json.gz'),'code':sha(Path(__file__)),'gold':sha(gold_path)}
    save(HERE/f'{stage}-results.json',summary_file)
    print(stage,len(rows),{a:round(v['full'],4) for a,v in summary.items()})
if __name__=='__main__':score(sys.argv[1])
