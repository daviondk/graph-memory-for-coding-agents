"""Post-hoc after primary grading: exact ordered structural token distance to canonical source."""
import ast,collections,gzip,json,random,sys
from live_score import L,strict_json
def events(x):
    if isinstance(x,ast.AST):
        yield ('node',type(x).__name__)
        for k,v in ast.iter_fields(x):
            yield ('field',k);yield from events(v)
        yield ('close','node')
    elif isinstance(x,list):
        yield ('list','start')
        for v in x:yield from events(v)
        yield ('close','list')
    else:yield ('value',type(x).__name__,repr(x))
def distance(a,b):
    # Trim identical prefix and suffix, then use exact unit-cost Myers bitvectors.
    start=0;n=len(a);m=len(b)
    while start<min(n,m) and a[start]==b[start]:start+=1
    while n>start and m>start and a[n-1]==b[m-1]:n-=1;m-=1
    a=a[start:n];b=b[start:m]
    if len(a)>len(b):a,b=b,a
    size=len(a)
    if not size:return len(b)
    alphabet={}
    for i,x in enumerate(a):alphabet[x]=alphabet.get(x,0)|(1<<i)
    pv=~0;mv=0;score=size;high=1<<(size-1)
    for x in b:
        eq=alphabet.get(x,0);xv=eq|mv;xh=(((eq&pv)+pv)^pv)|eq
        ph=mv|~(xh|pv);mh=pv&xh
        score+=bool(ph&high)-bool(mh&high)
        ph=(ph<<1)|1;mh=mh<<1;pv=mh|~(xv|ph);mv=ph&xv
    return score
def check():
    rng=random.Random(15)
    for _ in range(500):
        a=rng.choices(range(5),k=rng.randrange(33));b=rng.choices(range(5),k=rng.randrange(41));row=list(range(len(b)+1))
        for i,x in enumerate(a):
            prev=row;row=[i+1]
            for j,y in enumerate(b):row.append(min(row[-1]+1,prev[j+1]+1,prev[j]+int(x!=y)))
        assert distance(a,b)==row[-1]
def main():
    check();read=lambda n:json.loads((L/n).read_bytes())
    pred={(r['id'],r['arm']):r for r in read('capsule_calls/predictions.json')};scored={(r['id'],r['arm']):r for r in read('actions_scored.json')};per=[]
    for g in read('outcomes.json'):
        i=g['id'];path=L/'references'/(g['base_reference']['blob_sha256']+'.gz');base=gzip.decompress(path.read_bytes()).decode();source=gzip.decompress((L/'snapshots'/g['snapshot']).read_bytes()).decode()
        gs=list(events(ast.parse(base)));pre=distance(gs,list(events(ast.parse(source))))
        assert (pre==0)==(g['pre_ast_sha']==g['ref_ast_sha'])
        for a in ('joint','rebased_tail'):
            original=scored[i,a];changed=original['ast_change'];before=pre;after=before
            if changed:
                text=strict_json(pred[i,a]['answer']);assert source.count(text['old_str'])==1;af=source.replace(text['old_str'],text['new_str'],1);after=distance(gs,list(events(ast.parse(af))))
            per.append({'id':i,'arm':a,'before':before,'after':after,'direction':'closer' if after<before else 'farther' if after>before else 'same','changed':changed})
    val={}
    for name,rr in [('initially_different',[r for r in per if r['before']]),('initially_equal',[r for r in per if not r['before']])]:
        val[name]={a:dict(collections.Counter(r['direction'] for r in rr if r['arm']==a)) for a in ('joint','rebased_tail')}
    out={'descriptive':val,'per_case':per}
    if '--write-report' in sys.argv:(L/'distance.json').write_text(json.dumps(out,indent=1))
    else:assert out==read('distance.json')
    print('PASS',val)
if __name__=='__main__':main()
