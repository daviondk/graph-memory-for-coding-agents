"""Run the upstream sealed bounded writer unchanged on a disjoint roster, paired with unbounded conditions."""
import base64,collections,concurrent.futures,gzip,hashlib,importlib.util,json,os,re,sys,time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
AP=HERE.parent/'action_probe'
sys.path.insert(0,str(AP))
spec=importlib.util.spec_from_file_location('r5_frozen_bounded',AP/'bounded.py')
bound=importlib.util.module_from_spec(spec);spec.loader.exec_module(bound)
from shared import sha,write,save,read,rows
anchor=bound.anchor;pol=bound.pol;arms=('base','address','offset')
def digest(s):return hashlib.blake2b(s.encode('utf8','surrogatepass'),digest_size=16).hexdigest()
def package():
    sources=read(HERE/'sources_lock.json')
    assert all(sha(HERE/p)==v for p,v in sources['data'].items())
    for j in range(8):
        p=HERE/f'source_{j}.jsonl.gz'
        if not p.exists():os.link(HERE/f'source_{j}.gz',p)
    with gzip.open(HERE/'raw_pairs.jsonl.gz','wt',encoding='utf8',compresslevel=1) as g:
        for k in range(8):
            for q in rows(HERE/f'terminal_{k}.gz'):write(g,q)
def run(k):
    bound.D=bound.W=HERE
    cost=bound.run(k)
    bound.prior.advance=anchor.BASE_ADVANCE
    ct=collections.Counter()
    with gzip.open(HERE/f'unbounded_{k}.gz','wt',encoding='utf8',compresslevel=1) as f,gzip.open(HERE/f'confirmation_{k}.gz','wt',encoding='utf8') as verify:
        for task,(iid,observed) in zip(rows(HERE/f'source_{k}.gz'),rows(HERE/f'terminal_{k}.gz'),strict=True):
            assert iid==task['instance'];evs=task['events']
            ss={a:{'rebase':{}} for a in arms};meta={a:anchor.newmeta() for a in arms}
            cwd=True;tested=set()
            for t,(event,extra) in enumerate(zip(evs,observed,strict=True),1):
                ls=pol.readlines(extra,cwd)
                if extra:
                    cmd=extra['command']
                    cwd=False if re.search(r'(?:^|[;&\n])\s*(?:cd|pushd|popd)\b',cmd) else cwd
                    if re.fullmatch(r'\s*cd\s+/testbed/?\s*',cmd):cwd=True
                if ls:ct['parsed_steps']+=1
                ct['candidate_lines']+=len(ls);ct.update([m for p,n,v,m in ls]);ct['steps']+=1
                # Against future visible assertions at this step, compare pre-step evidence.
                _,args,obs=event;p=anchor.rel(args.get('path'))
                mapping={}
                if args.get('command')=='view' and p:
                    mapping={n:v for n,v in anchor.printed(obs).items()};kind='view'
                elif anchor.success(args.get('command'),p,obs) and (m:=anchor.unique_new(args,obs)):
                    first,block,pos=m;lo=first+block[:pos].count('\n');end=lo+args.get('new_str','').count('\n')
                    shift=args.get('new_str','').count('\n')-args['old_str'].count('\n')
                    mapping={n if n<lo else n-shift:v for n,v in anchor.printed(obs).items() if n<lo or n>end};kind='edit_neighbor'
                for n,v in mapping.items():
                    orig=ss['base']['rebase'].get(p,{}).get(n)
                    for a in ('address','offset'):
                        obsline=ss[a]['rebase'].get(p,{}).get(n)
                        if obsline is None or orig and orig[0]==obsline[0]:continue
                        key=(a,p,n,obsline[0])
                        if key in tested:continue
                        tested.add(key);write(verify,[iid,t,kind,a,p,n,obsline[0]==v])
                for a in arms:
                    anchor.anchored_advance(ss[a],meta[a],event,t)
                    if a!='base':
                        for p,n,line,_ in ls:ss[a]['rebase'].setdefault(p,{})[n+(a=='offset')]=[line,t]
                if t%4==0 and t<len(evs):
                    mapping={a:{p:[[n,digest(pair[0])] for n,pair in f0.items()] for p,f0 in ss[a]['rebase'].items()} for a in arms}
                    write(f,[iid,t,mapping])
    return cost,ct
def total():
    package();lk=read(AP/'bounded_method_lock.json')
    assert all(sha(Path(p))==h for p,h in lk['sources'].items())
    lockfiles=[HERE/'PROTOCOL.md',HERE/'BOUNDED_MATCH.md',HERE/'collect.py',HERE/'replicate.py',HERE/'evaluate.py',HERE/'roster_lock.json',HERE/'sources_lock.json',HERE/'raw_pairs.jsonl.gz',AP/'acquire.py',AP/'policy.py',AP/'bounded.py',AP/'bounded_method_lock.json',AP/'method_lock.json']
    save(HERE/'method_lock.json',{'utc':bound.stamp(),'files':{str(p):sha(p) for p in lockfiles},'policy':'upstream bounded.run unchanged'})
    assert not (HERE/'decisions_lock.json').exists()
    with concurrent.futures.ProcessPoolExecutor(3) as pool:out=list(pool.map(run,range(8)))
    blobs=[p for pat in ('bounded_cuts_*.gz','bounded_steps_*.gz','unbounded_*.gz','confirmation_*.gz') for p in HERE.glob(pat)]
    assert len(blobs)==32
    save(HERE/'decisions_lock.json',dict(utc=bound.stamp(),files={p.name:sha(p) for p in blobs},shard_cost=[v[0] for v in out],parser=dict(sum((k[1] for k in out),collections.Counter()))))
    print('sealed',len(blobs),flush=True)
if __name__=='__main__':total()
