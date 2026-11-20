"""Next verification targets from a compact per-episode procedure bank."""
import csv
from collections import Counter,defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import posixpath
import random
import re
import shlex
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from replay import effect,parse_read,split_cwd
from evaluate import dataset
def sha(b):return hashlib.sha256(b).hexdigest()
def save(n,x):(ROOT/n).write_text(json.dumps(x,ensure_ascii=False,indent=1)+'\n',encoding='utf8')
def read(n):return json.loads((ROOT/n).read_text(encoding='utf8'))
METHODS=['last','freq','failing','context']
SKIP={'__init__','conftest','models','test','tests','main','utils'}
def selector(cmd):
    cwd,body=split_cwd(cmd)
    if not cwd or '\n' in body:return None
    body=re.sub(r'\s+2>&1(?=\s|$)',' ',body)
    try:
        lexer=shlex.shlex(body,posix=True,punctuation_chars=';&|><');lexer.whitespace_split=True;lexer.commenters=''
        args=list(lexer)
    except ValueError:return None
    if not args:return None
    direct=True
    if '|' in args:
        k=args.index('|');suf=args[k+1:]
        if not suf or suf[0] not in ['head','tail','grep','rg','sed']:return None
        if any(c in suf for c in [';','&&','||','>','>>','&']):return None
        direct=False;args=args[:k]
    if not args or any(x in [';','&&','||','>','>>','&','<','<<'] for x in args):return None
    if args[0] in ['python','python3','python2'] or re.fullmatch(r'python\d\.\d+',args[0]):
        args=args[1:]
    if args[:1]==['-m']:args=args[1:]
    if not args:return None
    exe=args.pop(0)
    runner= 'pytest' if exe in ['pytest','py.test'] else 'django' if exe.split('/')[-1]=='runtests.py' else 'unittest' if exe=='unittest' else None
    if runner is None:return None
    targets=[];needle=None
    i=0
    while i<len(args):
        t=args[i];i+=1
        if t=='-k':
            if i>=len(args):return None
            needle=' '.join(args[i].split());i+=1
        elif t.startswith('-'):
            if '=' in t:continue
            if t in ['--tb','--maxfail','--durations','--color','--capture','--settings','--parallel','--verbosity','--ds','-p','-W','-o','-c','-n','-j']:
                if i>=len(args):return None
                i+=1
            elif t in ['--pdb','--lf','--last-failed','--failed-first','--ff','--collect-only','--co','-m','--ignore','--ignore-glob','--pyargs']:return None
            elif t in ['--disable-warnings','--no-header','--no-summary','--nomigrations','--reuse-db','--keepdb','--tb','--noinput','--no-input','--showlocals','--exitfirst','--strict-markers','--no-migrations','--no-cov','--']:pass
            elif not re.fullmatch(r'-[qvsxlf]+|-(?:n|j)\d+|-[rv][A-Za-z0-9]+',t):return None
        else:
            if not re.fullmatch(r'[A-Za-z0-9_./:+@\[\]-]+',t):return None
            if runner=='pytest' and not(any(q in t for q in ['/','.py','::']) or t in ['tests','test']):return None
            if runner in ['pytest','django'] and ('/' in t or '.py' in t or runner=='pytest'):
                first,*node=t.split('::')
                first=posixpath.normpath(posixpath.join(cwd,first))
                t='::'.join([first,*node])
            targets.append(t)
    if not targets:return None
    name=json.dumps([runner,sorted(set(targets)),needle],separators=(',',':'))
    return sha(name.encode()),name,direct and cwd=='/testbed'
def active_paths(cmd):
    op=parse_read(cmd)
    if op:return [op.path]
    status,changed=effect(cmd)
    return list(changed)
def context_key(context,prev):
    same=context&prev
    stem=lambda p:Path(p).stem
    return 2*len(same)+len({stem(p) for p in context}&{stem(p) for p in prev}-SKIP)
def predict():
    out=[];manifest=Counter()
    with gzip.open(ROOT/'predictions.jsonl.gz','wt',encoding='utf8') as f:
        for d in dataset():
            v=d['source'];bank={};recent=[];events=0
            for i,group in enumerate(d['groups']):
                query=[(j,selector(e['command'])) for j,e in enumerate(group)]
                q=[(j,x) for j,x in query if x is not None]
                if not q:
                    for e in group:
                        for p in active_paths(e['command']):
                            if p in recent:recent.remove(p)
                            recent.append(p);recent=recent[-6:]
                    continue
                if len(q)!=1:
                    manifest['multi_verify_batches']+=1
                    recent=[];continue
                j,actual=q[0];ct=set(recent)
                # Selection only accesses the prior bank, visible files and the global verification trigger.
                rank=sorted(bank,key=lambda k:-bank[k]['time'])
                pred={m:None for m in METHODS}
                if rank:
                    pred['last']=rank[0]
                    pred['freq']=max(rank,key=lambda k:bank[k]['n'])
                    pred['failing']=next((k for k in rank if bank[k]['fail']),rank[0])
                    pred['context']=max(rank,key=lambda k:context_key(ct,bank[k]['context']))
                f.write(json.dumps({'id':v['id'],'model':v['model'],'i':i,'j':j,'bank':rank,'choices':pred,'ctx':sorted(ct)},separators=(',',':'))+'\n')
                # The recipe may now be observed and its outer result is read after prediction.
                key=actual[0];r=group[j]['result']
                if len(bank)>=8 and key not in bank:del bank[rank[-1]]
                bank[key]={'time':i,'n':1+(bank[key]['n'] if key in bank else 0),'context':ct,'fail':bool(actual[2] and r and r['rc']==1)}
                recent=[];events+=1
            out.append({'id':v['id'],'model':v['model'],'eligible':events})
    save('exposure.json',out)
    save('lock.json',{'protocol':sha((ROOT/'PROTOCOL.md').read_bytes()),'code':sha(Path(__file__).read_bytes()),'predictions':sha((ROOT/'predictions.jsonl.gz').read_bytes()),'source_hash':sha((ROOT.parent/'sources.json').read_bytes()),'excluded':manifest})
def evaluate(check=False):
    lock=read('lock.json')
    assert sha(Path(__file__).read_bytes())==lock['code'] and sha((ROOT/'predictions.jsonl.gz').read_bytes())==lock['predictions']
    sums=defaultdict(Counter);tasks=defaultdict(Counter);true_rows=[];dicts={}
    with gzip.open(ROOT/'predictions.jsonl.gz','rt',encoding='utf8') as f:
        for d in dataset():
            v=d['source']
            for i,group in enumerate(d['groups']):
                q=[(j,selector(e['command'])) for j,e in enumerate(group)]
                q=[(j,x) for j,x in q if x is not None]
                if len(q)!=1:continue
                j,actual=q[0]
                r=json.loads(next(f));assert (r['id'],r['model'],r['i'],r['j'])==(v['id'],v['model'],i,j)
                bank=r['bank'];truth=actual[0];dicts[truth]=actual[1];a=r['choices'];repeat=truth in bank
                row={'n':1,'cold':int(not bank),'bank_contains':int(repeat),'chance':(1/len(bank) if repeat else 0),
                     'changed':int(a['last']!=a['context']),'wins':int(a['last']!=truth and a['context']==truth),'losses':int(a['last']==truth and a['context']!=truth),
                     **{m:int(a[m]==truth) for m in METHODS}}
                for k in ['pooled',v['model']]:sums[k].update(row)
                tasks[v['id'],v['model']].update(row)
                true_rows.append({'id':v['id'],'model':v['model'],'i':i,'j':j,'truth':truth})
        assert next(f,None) is None
    stats={}
    for name,s in sums.items():
        cases=defaultdict(Counter)
        for (iid,model),c in tasks.items():
            if name=='pooled' or name==model:cases[iid].update(c)
        arr=[(c['wins']-c['losses'],c['n']) for c in cases.values()]
        rng=random.Random(17112026);bs=[]
        for _ in range(3000):
            draws=rng.choices(arr,k=len(arr));bs.append(100*sum(a for a,b in draws)/sum(b for a,b in draws))
        bs.sort()
        stats[name]={**s,'issues_with_queries':len(cases),'sessions_with_queries':sum(1 for (_,m) in tasks if name=='pooled' or m==name),'delta_pp':100*(s['wins']-s['losses'])/s['n'],'issue_ci95':[bs[74],bs[2924]]}
    if check:assert stats==read('results.json') and dicts==read('recipes.json')
    else:
        save('results.json',stats);save('recipes.json',dicts)
        with gzip.open(ROOT/'reference.jsonl.gz','wt',encoding='utf8') as f:
            for z in true_rows:f.write(json.dumps(z,separators=(',',':'))+'\n')
        with (ROOT/'per_task.csv').open('w',newline='',encoding='utf8') as f:
            w=csv.writer(f);w.writerow(['id','model','n','last','freq','failing','context','wins','losses'])
            for (i,m),c in sorted(tasks.items()):w.writerow([i,m,*[c[k] for k in ['n','last','freq','failing','context','wins','losses']]])
    return stats
if __name__=='__main__':
    a=sys.argv[1]
    if a=='predict':predict()
    else:print(evaluate(a=='verify'))

