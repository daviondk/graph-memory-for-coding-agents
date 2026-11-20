"""Choose the read volume causally under the observed fixed reader's cumulative token cost."""
from concurrent.futures import ProcessPoolExecutor
import collections,gzip,hashlib,json,random,time
from common import *
from policy import *
from pipeline import snapshots,future
from analyze import interval
from verify import independent_hit
D=ROOT/'allocation'
PRICES=[0.,.00002,.00005,.0001,.0002,.0004,.0008,.0016,.0032,.0064,.0128,.0256]
ARMS=('fixed256','fixed512','fixed1024','scheduled','demand','value')
def j(name,x):(D/name).write_text(json.dumps(x,ensure_ascii=True,indent=1))
def source(s,k):return rows((ROOT/'source/test' if s=='cal' else D/'source')/f'{k}.jsonl.gz')
def options(args):
    s,k=args;m=json.loads((ROOT/'transfer/model.json').read_bytes())
    with gzip.open(D/s/f'{k}.jsonl.gz','wt',encoding='utf8',compresslevel=2) as f:
        for item in source(s,k):
            for t,ss,meta in snapshots(item):
                rs=pages(ss['rebase']);cs=costs(rs);fs=features(rs,meta,t,item['issue'],order(rs,meta)[:CAP]);props=proposals(rs,fs,m)
                ops={}
                for b in BUDGETS:
                    ids,toks=joint_fill(rs,cs,props,b);picked=set(ids)
                    ops[str(b)]={'pages':ids,'cost':toks,'mass':sum(v for span,v in props.items() if all(i in picked for i in span))}
                f.write(emit({'id':item['instance'],'cut':t,'pages':len(rs),'choices':ops})+'\n')
def incoming(s):
    for k in range(8):yield from rows(D/s/f'{k}.jsonl.gz')
def choose(op,available,mode,price,edges,step):
    feasible=[int(b) for b,c in op['choices'].items() if c['cost']<=available]
    assert 512 in feasible
    if mode=='value':return max(feasible,key=lambda n:(op['choices'][str(n)]['mass']-price*op['choices'][str(n)]['cost'],-op['choices'][str(n)]['cost'],-n))
    if mode=='scheduled':target=[256,256,1024][step%3]
    elif mode=='demand':target=256 if op['pages']<=edges[0] else 1024 if op['pages']>=edges[1] else 512
    else:raise ValueError(mode)
    return max((n for n in feasible if n<=target),default=min(feasible))
def simulate(opps,price,edges,arms=ARMS):
    rows_=[];current=None
    for o in opps:
        if current!=o['id']:
            current=o['id'];step=0;bal=Counter();spent=Counter()
        base=o['choices']['512']['cost'];dec={}
        for arm in arms:
            available=min(1536,bal[arm]+base)
            if arm.startswith('fixed'):budget=int(arm[5:])
            else:budget=choose(o,available,arm,price,edges,step)
            ck=o['choices'][str(budget)]['cost'];spent[arm]+=ck;bal[arm]=available-ck
            if not arm.startswith('fixed'):assert bal[arm]>=0
            dec[arm]={'budget':budget,'cost':ck,'balance':bal[arm] if not arm.startswith('fixed') else None,'cumulative':spent[arm]}
        rows_.append({'id':o['id'],'cut':o['cut'],'actions':dec});step+=1
    return rows_
def labels(s):
    outcome={}
    for k in range(8):
        packets=iter(rows(D/s/f'{k}.jsonl.gz'))
        for item in source(s,k):
            for t,ss,meta in snapshots(item):
                o=next(packets);assert (item['instance'],t)==(o['id'],o['cut'])
                tar=future(item['events'],t)
                if tar:
                    rs=pages(ss['rebase']);outcome[item['instance'],t]={'accepted':tar[2],'hits':{b:int(independent_hit([rs[i] for i in ch['pages']],tar[0],tar[1])) for b,ch in o['choices'].items()}}
        assert next(packets,None) is None
    return outcome
def evaluate(ds,gold):
    ca=Counter();selected=collections.defaultdict(Counter);n=Counter();rows_=[]
    for o in ds:
        g=gold.get((o['id'],o['cut']));n['cuts']+=1;n['intents']+=g is not None;n['accepted']+=int(bool(g and g['accepted']))
        marks={}
        for a,action in o['actions'].items():
            b=str(action['budget']);ca[a]+=action['cost'];selected[a][b]+=1
            if g and g['accepted']:marks[a]=[g['hits'][b],action['cost']]
            if not a.startswith('fixed'):assert action['cumulative']<=o['actions']['fixed512']['cumulative'] if 'fixed512' in o['actions'] else True
        if marks:rows_.append({'id':o['id'],'repo':o['id'].split('.')[0],'metrics':{'alloc':marks}})
    hit={a:sum(r['metrics']['alloc'][a][0] for r in rows_) for a in selected}
    return {'counts':dict(n),'tokens_all_cuts':dict(ca),'budget_counts':{k:dict(v) for k,v in selected.items()},'hits':hit},rows_
def main():
    start=time.monotonic()
    for s in ['cal','test']:
        (D/s).mkdir(exist_ok=True)
        with ProcessPoolExecutor(3) as ex:list(ex.map(options,[(s,k) for k in range(8)]))
        opts=list(incoming(s))
        if s=='cal':
            gd=labels(s);p=sorted(o['pages'] for o in opts);edges=[p[len(p)//3],p[len(p)*2//3]]
            records={};best=None
            for price in PRICES:
                ds=simulate(opts,price,edges,['fixed512','value'])
                summ,_=evaluate(ds,gd);records[str(price)]=summ
                score=(summ['hits']['value'],-price)
                if best is None or score>best:best=score
            pr=-best[-1];ds=simulate(opts,pr,edges);cal,_=evaluate(ds,gd)
            comparator=max(['fixed512','scheduled','demand'],key=lambda a:cal['hits'][a])
            j('training.json',{'price':pr,'page_tertiles':edges,'simple_control':comparator,'calibration':cal,'grid':records})
        else:
            co=json.loads((D/'training.json').read_bytes());ds=simulate(opts,co['price'],co['page_tertiles'])
            with gzip.open(D/'decisions.jsonl.gz','wt',encoding='utf8') as f:
                for o in ds:f.write(emit(o)+'\n')
            files=[ROOT/'allocation_run.py',ROOT/'allocation_extract.py',D/'PROTOCOL.md',D/'training.json',D/'selection.json',D/'decisions.jsonl.gz',ROOT/'transfer/model.json',*sorted((D/'source').glob('*.gz')),*sorted((D/'test').glob('*.gz'))]
            j('prediction_lock.json',{str(f.relative_to(ROOT)).replace('\\','/'):digest(f) for f in files})
            gd=labels(s);res,casewise=evaluate(ds,gd);res['value_contrasts']={c:interval(casewise,'value',c,'repo','alloc') for c in ['fixed256','fixed512','fixed1024','scheduled','demand']};res['validation_selected']=co['simple_control'];res['wall_seconds']=time.monotonic()-start
            res['tasks']=len(set(o['id'] for o in opts));res['repos']=len(set(o['id'].split('.')[0] for o in opts));res['tasks_with_accepted']=len(set(r['id'] for r in casewise))
            j('results.json',res)
            with gzip.open(D/'metrics.jsonl.gz','wt',encoding='utf8') as f:
                for r in casewise:f.write(emit(r)+'\n')
            print(res,flush=True)
if __name__=='__main__':main()
