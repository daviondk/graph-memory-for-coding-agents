"""Standalone stdlib cross-check of endpoints, token equality, all answers and paired contrasts."""
from collections import Counter
import gzip,hashlib,json,math,re,string,struct
from pathlib import Path
D=Path(__file__).resolve().parent
R46=D.parents[1]/'graph_memory_round46/reader_transfer'
L=R46.parent/'reader_length'
def get(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def toks(s):return re.sub(r'\b(a|an|the)\b',' ',''.join(x for x in s.lower() if x not in string.punctuation)).split()
def score(ans,refs):
    x=toks(ans);em=f=0
    for a in refs:
        y=toks(a);v=sum((Counter(x)&Counter(y)).values())
        em=max(em,x==y);f=max(f,2*v/(len(x)+len(y)) if x or y else 1)
    return em,f
def close(a,b):return math.isclose(a,b,rel_tol=0,abs_tol=1e-11)
def main():
    if (D/'manifest.json').exists():
        assert get(D/'manifest.json')['files']=={p.name:sha(p) for p in D.iterdir() if p.is_file() and p.name!='manifest.json'}
    plan=get(D/'registration.json');order=get(D/'orders.json.gz');contexts=get(D/'contexts.json.gz');prompts=get(D/'prompts.json.gz')
    gold=get(R46/'grading-view.json.gz');old=get(L/'answers.json.gz');full=get(D/'answers.json.gz')
    assert plan['protocol']==sha(D/'PROTOCOL_RU.md') and plan['base']==sha(R46/'manifest.json') and plan['long']==sha(L/'manifest.json')
    sol=get(D/'outcomes.json.gz');r=get(D/'results.json');seal=get(D/'answer-seal.json')
    assert r['answers']==sha(D/'answer-seal.json') and seal['answers']==sha(D/'answers.json.gz')
    assert set(order)==set(contexts)==set(sol)==set(gold) and set(full)==set(prompts)
    for k,seq in prompts.items():
        assert hashlib.sha256(struct.pack('<'+'I'*len(seq),*seq)).hexdigest()==k
        if k in old:assert old[k]==full[k]
    count=swapped=0
    for q,g in order.items():
        ranked=g['order'];true=int(g['true']);base=int(g['lex']);assert ranked[0]==base
        ctx=contexts[q];edges=g['edges'];assert true==next((v for v in ranked if str(v) in edges),base)
        expected={'true':true,'lex':base}
        for seed,rec in g['sham'].items():
            e=rec['edges'];owners=rec['owners'];assert set(owners)==set(edges)
            assert {str(new):edges[j] for j,new in owners.items()}==e
            new=next((v for v in ranked if str(v) in e),base);assert new==rec['second'] and (new==base)==(true==base)
            swapped+=new!=true
            if new!=true:assert str(new) not in edges
            expected['sham'+seed]=new
        lens={len(prompts[k]) for _,k,n in ctx['refs'].values()};assert len(lens)==1
        refs,support=gold[q]
        for a,(idx,k,n) in ctx['refs'].items():
            assert idx==expected[a] and n==len(prompts[k])
            val=sol[q]['arms'][a];em,f=score(full[k]['answer'],refs)
            assert close(val[0],em) and close(val[1],f) and val[2]==(set(support)<={g['seed'],idx})
            count+=1
    assert count==7168
    for group,fn in [('all',lambda r:True),('switched',lambda r:r['switch']),('substituted',lambda r:r['successful'])]:
        rows=[v for v in sol.values() if fn(v)]
        for pair,contrast in r['groups'][group]['contrasts'].items():
            a,b=pair.split('-')
            for j in range(4):
                def val(v,k):return sum(v['arms']['sham'+str(s)][j] for s in plan['seeds'])/5 if k=='sham' else v['arms'][k][j]
                ds=[val(v,a)-val(v,b) for v in rows]
                assert close(100*sum(ds)/len(ds),contrast['pp'][j])
                assert sum(x>1e-12 for x in ds)==contrast['wins'][j] and sum(x< -1e-12 for x in ds)==contrast['losses'][j]
    print('verified',count,'logical answers,',len(full),'unique prompts,',swapped,'redirected top choices')
if __name__=='__main__':main()
