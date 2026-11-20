"""Independent black-box input generators. No access to model candidates or grading data."""
import ast,collections,hashlib,itertools,json,math,random,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
UP=Path('D:/CodexResearch/x20-session3-quixbugs')
def sha(b):return hashlib.sha256(b).hexdigest()
def canon(x):return json.dumps(x,sort_keys=True,ensure_ascii=True,separators=(',',':'))
def save(p,x):(ROOT/p).write_text(json.dumps(x,indent=1,ensure_ascii=True),encoding='utf8')
def load(p):return json.loads(p.read_text(encoding='utf8'))
def gen(name,r,j):
    n=3+j%6
    arr=lambda:[r.randint(-6,6) for _ in range(n)]
    if name=='bitcount':
        b=r.randrange(6,60);return [(1<<b)+r.choice([-3,-1,0,1,3,r.randrange(8,200)])]
    if name=='bucketsort':
        k=r.randint(3,17);return [[r.choice([0,k-1,r.randrange(k)]) for _ in range(n)],k]
    if name.startswith('find_') and name.endswith('_sorted'):
        xs=sorted(arr());return [xs,[xs[0]-r.randrange(1,4),xs[-1]+1,r.choice(xs),xs[0],xs[-1]][j%5]]
    if name=='flatten':
        x,y,z=arr()[:3];return [[x,[[],[y]],[[[z],[str(j)]]],[],False]]
    if name=='gcd':
        f=r.randint(2,60);return [[f*r.randint(1,80),f*r.randint(1,40)],[f,0],[0,f],[f,f]][j%4]
    if name=='get_factors':
        ps=[2,3,5,7,11,13,17,19,23,29,31,37,41,43];return [math.prod(r.choices(ps,k=1+j%4))]
    if name=='hanoi':
        a,b=r.sample([1,2,3],2);return [1+j%5,a,b]
    if name=='is_valid_parenthesization':
        a=r.randint(2,8); b=r.randint(1,5)
        valid='('*a+'()'*b+')'*a
        return [[valid,'()'*b+valid,valid[:-1],')'+valid,'()'*a+')(('+')'*b][j%5]]
    if name=='kheapsort':
        k=r.randint(1,n);xs=sorted(r.sample(range(-45,46),n))
        blocks=[xs[i:i+k] for i in range(0,n,k)]
        for b in blocks:r.shuffle(b)
        return [sum(blocks,[]),k]
    if name=='kth':return [arr(),r.randrange(n)]
    if name in ('lcs_length','longest_common_subsequence'):
        word=lambda:''.join(r.choices('abcd',k=n));x,y=word(),word()
        return [(x+'b' if j%3==0 else x),[y,x[::-1],y+'ab'][j%3]]
    if name=='lis':return [r.sample(range(-30,30),n)]
    if name=='max_sublist_sum':
        xs=arr();return [[xs,[-abs(x)-1 for x in xs],[-20]+xs+[8]][j%3]]
    if name in ('quicksort','mergesort'):
        xs=arr();return [[xs,sorted(xs,reverse=True),xs+[xs[0]],sorted(xs)][j%4]]
    if name=='next_palindrome':
        if j%5==0:return [[9]*(1+j//5%5)]
        half=str(r.randrange(11,99));return [list(map(int,half+(str(r.randrange(10)) if j%2 else '')+half[::-1]))]
    if name=='next_permutation':
        xs=r.sample(range(-12,13),3+j%4)
        if xs==sorted(xs,reverse=True):xs=xs[::-1]
        return [xs]
    if name=='pascal':return [r.randint(5,38)]
    if name=='possible_change':return [sorted(r.sample(range(1,10),1+j%4)),r.randrange(2,28)]
    if name=='powerset':return [r.sample(list(range(-10,18)),2+j%5)]
    if name=='rpn_eval':
        a,b,c=[float(x) for x in r.sample(range(2,25),3)]
        return [[[a,b,'-',c,'/'],[a,b,'/',c,'+'],[a,b,c,'*','-'],[a,c,'+',b,'*']][j%4]]
    if name=='shunting_yard':
        xs=r.sample(range(1,30),4);ops=r.choices(['+','-','*','/'],k=3)
        return [[v for pair in zip(xs,ops) for v in pair]+[xs[-1]]]
    if name=='sieve':return [r.randrange(11,181)]
    if name=='sqrt':return [r.uniform(1.1,90.0),r.choice([1e-4,1e-5,1e-6])]
    if name=='subsequences':
        start=r.randrange(-10,12);return [start,start+n,r.randint(1,n)]
    if name=='to_base':return [r.randint(1,200000),r.choice([2,3,7,8,10,16,23,36])]
    if name=='wrap':
        width=r.randint(7,15);words=[''.join(r.choices('abcde',k=r.randint(1,width//2))) for _ in range(3+j%7)]
        return [' '.join(words),width]
    raise KeyError(name)
def main():
    names=[r['name'] for r in load(ROOT.parent/'roster.json') if r['eligible']]
    cases={};manifest={}; docs={}
    for name in names:
        path=UP/'python_programs'/(name+'.py');source=path.read_text(encoding='utf8');tree=ast.parse(source)
        params=[a.arg for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name for a in n.args.args]
        public={canon(json.loads(l)[0]) for l in (UP/'json_testcases'/(name+'.json')).read_text(encoding='utf8').splitlines()}
        examples=[]
        for line in source.splitlines():
            if '>>>' not in line:continue
            try:
                for call in ast.walk(ast.parse(line.split('>>>',1)[1].strip())):
                    if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Name) or call.func.id!=name:continue
                    args=list(map(ast.literal_eval,call.args))
                    kwargs={kw.arg:ast.literal_eval(kw.value) for kw in call.keywords}
                    args.extend(kwargs[p] for p in params[len(args):] if p in kwargs)
                    examples.append(args)
            except (SyntaxError,TypeError,ValueError):pass
        excluded=public|{canon(args) for args in examples}
        if name=='hanoi':
            for key in list(excluded):
                xs=json.loads(key)
                if len(xs)<3:excluded.add(canon(xs+([1,3] if len(xs)==1 else [3])))
        r=random.Random(int(sha(('quix-property-v1'+name).encode())[:16],16))
        rows=[];seen=set()
        for j in range(400):
            args=gen(name,r,j);key=canon(args)
            if key in excluded or key in seen:continue
            seen.add(key)
            rows.append({'input':args,'key':sha(key.encode()),'generator_index':j})
            if len(rows)==16:break
        assert len(rows)==16,(name,len(rows))
        cases[name]=rows;docs[name]={'public_input_count':len(public),'parsed_examples':examples,'excluded_overlap':len(seen&excluded),'inputs':len(rows)}
        manifest[name]={'buggy_program_sha256':sha(path.read_bytes()),'public_cases_sha256':sha((UP/'json_testcases'/(name+'.json')).read_bytes())}
    save('cases.json',cases);save('generation.json',{'upstream':manifest,'filters':docs,'programs':len(names),'cases':sum(map(len,cases.values()))})
if __name__=='__main__':main()
