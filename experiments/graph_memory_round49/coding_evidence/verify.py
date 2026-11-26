"""Recompute all original and expanded test statuses, gateway costs, and memory ranking offline."""
import collections,gzip,hashlib,json,math,re,sys
from pathlib import Path
from suite import parse
D=Path(__file__).resolve().parent
def h(data):return hashlib.sha256(data).hexdigest()
def read(n):
    b=(D/n).read_bytes()
    return json.loads(gzip.decompress(b) if n.endswith('.gz') else b)
def size(s):return len(s.encode())
def ranks():
    evidence=read('evidence.json.gz');graph=read('history.json')
    docs={};quotes={}
    def tok(x):return re.findall(r'[a-z]{2,}',re.sub(r'([a-z])([A-Z])',r'\1 \2',x).lower())
    for p,l,n,s in evidence:
        k=(p,l,n);docs[k]=tok(s)+tok(p+' '+n)*2
        quotes[k]=(f'{p}:{l}  {n}\n'+s).encode()[:399].decode('utf8','ignore')+'\n'
    assert set(docs)=={tuple(k) for k,_ in graph['visits']}
    target=next(v['problem_statement'] for v in read('screen.json')['rows'] if v['instance_id']=='alteryx__woodwork-640')
    tally=collections.Counter(tok(target));vocab=collections.Counter(t for d in docs.values() for t in set(d))
    mean=sum(map(len,docs.values()))/len(docs);scores={}
    for v,d in docs.items():
        count=collections.Counter(d);scores[v]=sum(f*math.log1p((len(docs)-vocab[t]+.5)/(vocab[t]+.5))*2.2*count[t]/(count[t]+1.2*(.25+.75*len(d)/mean)) for t,f in tally.items() if count[t])
    edge=collections.defaultdict(dict)
    for a,b,n in graph['calls']:edge[tuple(a)][tuple(b)]=math.log1p(n)
    z=sum(x+.01 for x in scores.values());start={v:(x+.01)/z for v,x in scores.items()};current=start.copy()
    for _ in range(200):
        lost=sum(w for v,w in current.items() if not edge[v]);nxt={v:(.4+.6*lost)*w for v,w in start.items()}
        for a,w in current.items():
            total=sum(edge[a].values())
            for b,ew in edge[a].items():nxt[b]+=.6*w*ew/total
        if max(abs(nxt[v]-current[v]) for v in docs)<1e-13:break
        current=nxt
    m=read('packet-seal.json');texts={}
    for name,s in [('graph',nxt),('flat',scores)]:
        chosen=sorted(docs,key=lambda v:(-s[v],v))[:4];assert list(map(list,chosen))==m['chosen'][name]
        texts[name]=''.join(quotes[v] for v in chosen).encode()
    limit=min(map(len,texts.values()));assert m['memory_bytes']==limit
    texts={k:b[:limit].decode('utf8','ignore').encode() for k,b in texts.items()};texts['none']=b''
    assert {k:h(v) for k,v in texts.items()}==m['digest']
    return texts
def main():
    if (D/'manifest.json').exists():
        for n,v in read('manifest.json')['files'].items():assert h((D/n).read_bytes())==v,n
    texts=ranks()
    sys.path.insert(0,str(D/'inputs/vendor'))
    from log_parsers import parse_log_pytest
    hidden=read('inputs/grade-case.json.gz');lk=read('locked.json');grade=read('grading/scores.json');sg=read('grade-seal.json')
    assert sg['lock']==grade['lock_sha256']==h((D/'locked.json').read_bytes())
    for n,v in sg['files'].items():assert h((D/'grading'/n).read_bytes())==v
    roles={'fail_to_pass':'FAIL_TO_PASS','pass_to_pass':'PASS_TO_PASS'}
    ids=set(hidden['FAIL_TO_PASS']+hidden['PASS_TO_PASS']);assert len(ids)==55
    extended=read('suite/profiles.json.gz');summary=read('suite/summary.json')
    for mode,o in grade['outcomes'].items():
        b=(D/'grading'/(mode+'.log')).read_bytes();assert h(b)==o['log_sha256']
        statuses=parse_log_pytest(b.decode());passed={n for n,v in statuses.items() if v=='PASSED'}
        assert (ids==passed)==o['official_exact']
        for role,field in roles.items():
            tests=hidden[field]
            assert o['registered_statuses'][role]=={a:statuses[a] for a in tests}
            assert o['f2p' if role=='fail_to_pass' else 'p2p']==[len(passed.intersection(tests)),len(tests)]
        expected=b'' if mode=='base' else hidden['patch'].encode() if mode=='reference' else (D/lk['cases'][mode]['path']).read_bytes()
        assert h(expected)==o['patch_sha256']
        assert o['test_patch_sha256']==h(hidden['test_patch'].encode())
        for ext in ('xml','log'):
            source=gzip.decompress((D/'suite'/(mode+'.'+ext+'.gz')).read_bytes());assert h(source)==summary[mode][ext+'_sha256']
            if ext=='xml':states=parse(source)
        assert extended[mode]==states and len(states)==424
        assert all(states[k]==statuses[k] for k in ids)
        assert all(states[k]==extended['base'][k] for k in states.keys()-ids)
        assert dict(collections.Counter(states.values()))==summary[mode]['status']
    events=read('responses.json.gz');stats=read('profiles.json')
    for k,v in stats.items():
        trace=events[k];ops=collections.Counter();delivered=collections.Counter();charged=collections.Counter();paths=set()
        assert v['patch_sha256']==grade['outcomes'][k]['patch_sha256'] and trace[0]['response']['memory'].encode()==texts[v['condition']]
        for x in trace:
            op=x['request']['op'];ops[op]+=1;r=x['response'];delivered[op]+=size(json.dumps(r,ensure_ascii=False))
            if op in ('read','list','search') and 'text' in r:
                assert size(r['text'])==r['charged_bytes'];charged[op]+=r['charged_bytes']
            if op=='read' and 'text' in r:paths.add(x['request']['path'])
            if op=='start' and 'memory' in r:charged['memory']+=size(r['memory'])
        assert charged==v['charged'] and ops==v['operations'] and sum(charged.values())==v['gateway_bytes']<=16000
        assert sorted(paths)==v['read_paths'] and delivered==v['responses_by_op'] and sum(delivered.values())==v['response_json_body_bytes']
    print('Verified two ranked memories, 5 x 55 official and 5 x 424 expanded test statuses, and 3 metered sessions.')
if __name__=='__main__':main()
