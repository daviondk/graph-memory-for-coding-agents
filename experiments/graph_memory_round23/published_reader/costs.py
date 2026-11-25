"""Matched CPU stage costs with actual source-to-output checks for every call."""
from inputs import *
from importlib.util import spec_from_file_location,module_from_spec
from time import perf_counter_ns as clock
from statistics import median
spec=spec_from_file_location('published_predictor',HERE/'predict.py')
pred=module_from_spec(spec);spec.loader.exec_module(pred)
METHODS=('whole','fine','verbatim_core')
def prepare():
    s=load(HERE/'plan.json')['selection']['test']
    ordered=sorted(s,key=lambda r:h(('r23-published-timing|'+r['t']).encode()))
    rec={'study':sha(HERE/'analysis-lock.json'),'protocol':sha(HERE/'COST_RU.md'),'code':sha(Path(__file__)),'qids':[r['q'] for r in ordered[:24]],'warmup':ordered[24]['q'],'replicates':2,'read_gold':False}
    p=HERE/'cost-plan.json'
    if p.exists():assert load(p)==rec
    else:
        assert not (HERE/'test-results.json').exists();save(p,rec)
    return rec
def one_input(q,ranks):
    obj=load(PRIVATE/'test'/f'{q[6:]}.json.gz');r=load(HERE/'forecasts/test'/f'{q[6:]}.json.gz')
    raw=load(rd.stream.CACHE/f"{obj['i']}-{obj['t']}.json.gz");model=load(FINE)['models']['full']
    pool=ranks[q];ad=obj['ad'];fields=obj['fields'];parents=obj['parents']
    blocks=[[e,a,b,c,len(fields[str(e)][a:b].encode())] for e,a,b,c,r,p in obj['blocks']]
    local={'addresses':ad,'blocks':blocks}
    return obj,r,raw,model,pool,blocks,local
def experiment():
    plan=prepare();assert (HERE/'test-seal.json').exists()
    qs=set(plan['qids']+[plan['warmup']]);ranks={}
    for i in range(8):
        for r in load(roots('test',i)[0]):
            if r['q'] in qs:ranks[r['q']]=r['rr'][:16]
    assert set(ranks)==qs
    model,tok,e5=pred.reader()
    def timed(m,o):
        obj,rec,raw,coef,rr,blocks,local=o
        fields=obj['fields'];parents=obj['parents'];query=obj['query']
        now=clock()
        if m=='whole':order=parents
        elif m=='fine':
            geom=rd.geometry(local,raw,rr);x,_,_=rd.features(query,rr,blocks,geom)
            z=x[:,coef['columns']]
            p=1/(1+np.exp(-np.clip((z-coef['mean'])/coef['scale']@coef['coef']+coef['offset'],-200,200)))
            sort=sorted(range(len(blocks)),key=lambda j:(-p[j]/blocks[j][3],j))
            order=parents[:2]+[blocks[j][:3] for j in sort]
        else:
            scored=[]
            for j,(e,a,b) in enumerate(parents):
                ctx=fields[str(e)][a:b]
                result=model.process(query,ctx,threshold=.2,min_span_chars=30)
                for s in result['spans']:
                    l,h=s['start'],s['end'];assert ctx[l:h]==s['text']
                    scored.append((-s['score'],j,l,[e,a+l,a+h]))
            order=parents[:2]+[z[3] for z in sorted(scored)]
        selected=pred.render(order,fields,e5);elapsed=clock()-now
        assert selected==rec['picks'][m]
        return elapsed,selected['context_sha']
    warm=one_input(plan['warmup'],ranks)
    for m in METHODS:timed(m,warm)
    records=[];jobs=[(q,one_input(q,ranks)) for q in plan['qids']]
    for rep in range(2):
        for j,(q,o) in enumerate(jobs):
            shift=(j+rep)%len(METHODS);order=METHODS[shift:]+METHODS[:shift]
            if rep:order=order[::-1]
            for pos,m in enumerate(order):
                ns,d=timed(m,o);records.append({'q':q,'t':o[0]['t'],'repeat':rep,'position':pos,'method':m,'ns':ns,'context_sha':d})
            print('costs',rep+1,j+1,flush=True)
    save(HERE/'cost-timings.json.gz',records)
    stats={}
    for m in METHODS:
        data=[r['ns']/1e6 for r in records if r['method']==m]
        stats[m]={'p50_ms':float(np.quantile(data,.5)),'p95_ms':float(np.quantile(data,.95)),'mean_ms':float(np.mean(data))}
    ratio={}
    for a in ['whole','fine']:
        per=[]
        for q in plan['qids']:
            med=lambda m:median(r['ns'] for r in records if r['q']==q and r['method']==m)
            per.append(med('verbatim_core')/med(a))
        ratio['verbatim_core/'+a]={'median':median(per),'min':min(per),'max':max(per)}
    save(HERE/'cost-results.json',{'n':24,'calls':len(records),'warmup_excluded':plan['warmup'],'plan':sha(HERE/'cost-plan.json'),'times':sha(HERE/'cost-timings.json.gz'),'ms':stats,'paired_latency_ratios':ratio})
if __name__=='__main__':
    prepare()
    if len(sys.argv)>1:experiment()
