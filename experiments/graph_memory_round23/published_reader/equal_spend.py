"""Apply equal query-dependent token ceilings, using sealed predictions as cost instruments."""
from inputs import *
from tokenizers import Tokenizer
import importlib.util
spec=importlib.util.spec_from_file_location('r23_verbatim_score',HERE/'score.py')
score_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(score_module)
groups,measure,compare=score_module.groups,score_module.measure,score_module.compare
def subtract(a,b,prior):
    out=[]
    for l,h in sorted(prior):
        if h<=a:continue
        if l>=b:break
        if l>a:out.append([a,min(l,b)])
        a=max(a,h)
    if a<b:out.append([a,b])
    return out
def pack(candidates,fields,tok,budget):
    txt='';picked=[];covered=defaultdict(list);paid=0
    for e,a,b in candidates:
        extra=subtract(a,b,covered[e])
        if not extra:continue
        pieces=[fields[str(e)][l:h] for l,h in extra]
        ctx='\n'.join(([txt] if txt else [])+pieces)
        cost=len(tok.encode(ctx,add_special_tokens=False).ids)
        if cost>budget:continue
        txt=ctx;paid=cost;covered[e].extend(extra);picked.extend([[e,l,h] for l,h in extra])
    assert paid==len(tok.encode(txt,add_special_tokens=False).ids)<=budget
    return {'tokens':paid,'spans':picked,'context_sha':h(txt.encode())}
def lock():
    target=HERE/'equal-spend-plan.json'
    code={'code':sha(Path(__file__)),'notes':sha(HERE/'EQUAL_SPEND_RU.md'),'parent':sha(HERE/'plan.json')}
    if target.exists():assert load(target)==code
    else:
        assert not (HERE/'test-results.json').exists() and not (HERE/'test-seal.json').exists()
        save(target,code)
def forecast(stage):
    lock();seal=load(HERE/f'{stage}-seal.json');tok=Tokenizer.from_file(str(E5));rows=[]
    for q,chk in sorted(seal['files'].items()):
        p=HERE/'forecasts'/stage/f'{q[6:]}.json.gz';r=load(p);assert sha(p)==chk
        sp=PRIVATE/stage/f'{q[6:]}.json.gz';assert sha(sp)==r['input'];s=load(sp)
        primary=r['picks']['verbatim_core'];cap=primary['tokens'];parents=s['parents'];blocks=s['blocks']
        rank=sorted(enumerate(blocks),key=lambda zr:(-zr[1][5],zr[0]))
        fine=parents[:2]+[b[:3] for _,b in rank]
        # Identity on the parent ceiling verifies matching semantics independently.
        for name,order in [('fine',fine),('whole',parents)]:
            assert pack(order,s['fields'],tok,2048)==r['picks'][name]
        out={'verbatim_core':primary,'fine':pack(fine,s['fields'],tok,cap),'whole':pack(parents,s['fields'],tok,cap)}
        assert all(x['tokens']<=cap for x in out.values())
        rows.append({'q':q,'t':r['t'],'ad':r['ad'],'picks':out,'cap':cap})
    p=HERE/f'{stage}-equal-spend-forecasts.json.gz';save(p,rows)
    save(HERE/f'{stage}-equal-spend-seal.json',{'predictions':sha(p),'main_seal':sha(HERE/f'{stage}-seal.json'),'plan':sha(HERE/'equal-spend-plan.json')})
def score(stage):
    lock();p=HERE/f'{stage}-equal-spend-forecasts.json.gz';receipt=load(HERE/f'{stage}-equal-spend-seal.json');assert sha(p)==receipt['predictions']
    gold=load(R19/'write_transfer/gold-spans.json.gz' if stage=='dev' else WORK/'graph_memory_round18/isetrace_official/gold-spans.json.gz')
    rows=[]
    for r in load(p):
        q=r['q'];truth=groups([((s['event_id'],s['json_pointer']),s['char_start'],s['char_end']) for s in gold[q]])
        vals={}
        for a,data in r['picks'].items():
            m=measure([(r['ad'][e],l,h) for e,l,h in data['spans']],truth)
            vals[a]={**m,'tokens':data['tokens']}
        rows.append({'q':q,'t':r['t'],'cap':r['cap'],'scores':vals})
    assert len(rows)==len({r['t'] for r in rows})
    outcomes=HERE/f'{stage}-equal-spend-outcomes.json.gz';save(outcomes,rows)
    measures={a:{k:sum(r['scores'][a][k] for r in rows)/len(rows) for k in vals[a]} for a in vals}
    diffs={a:compare(rows,a,'verbatim_core') for a in ('fine','whole')}
    save(HERE/f'{stage}-equal-spend-results.json',{'measures':measures,'n':len(rows),'pairs_against_verbatim':diffs,'per_query':sha(outcomes),'forecast_seal':sha(HERE/f'{stage}-equal-spend-seal.json')})
if __name__=='__main__':
    if len(sys.argv)==1:lock()
    else:
        stage=sys.argv[1];forecast(stage);score(stage)
