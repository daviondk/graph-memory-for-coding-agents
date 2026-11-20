"""Public properties; only trusted parent/scorer evaluates these predicates."""
import ast,collections,itertools,math,operator,re,string

def sublists(xs):
    return (list(x) for size in range(len(xs)+1) for x in itertools.combinations(xs,size))

def subseq(s,t):
    it=iter(t)
    return all(any(x==y for y in it) for x in s)

def prime(n):
    return n>=2 and all(n%i for i in range(2,math.isqrt(n)+1))

def valid(name,args,result):
    a=args[0]; b=args[1] if len(args)>1 else None; v=result
    def ints(seq):return isinstance(seq,list) and all(type(i) is int for i in seq)
    def exact(w):
        if type(w) is int:return type(v) is int and w==v
        if type(w) is bool:return type(v) is bool and w==v
        return type(w) is type(v) and v==w
    if name=='bitcount':return exact(a.bit_count())
    if name in ('bucketsort','mergesort','quicksort','kheapsort'):return ints(v) and v==sorted(a)
    if name=='find_first_in_sorted':return exact(a.index(b) if b in a else -1)
    if name=='find_in_sorted':return type(v) is int and ((0<=v<len(a) and a[v]==b) or (v==-1 and b not in a))
    if name=='flatten':
        def leaves(x):
            if isinstance(x,list):return [v for y in x for v in leaves(y)]
            return [x]
        w=leaves(a)
        return isinstance(v,list) and len(v)==len(w) and all(type(k) is type(l) and k==l for k,l in zip(v,w))
    if name=='gcd':return exact(math.gcd(a,b))
    if name=='get_factors':return ints(v) and sorted(v)==v and all(map(prime,v)) and math.prod(v)==a
    if name=='hanoi':
        n,src,dst=args;pegs={p:(list(range(n,0,-1)) if p==src else []) for p in (1,2,3)}
        if not isinstance(v,list) or len(v)!=2**n-1:return False
        for step in v:
            if not ints(step) or len(step)!=2:return False
            i,j=step
            if i==j or i not in pegs or j not in pegs or not pegs[i]:return False
            disk=pegs[i].pop()
            if pegs[j] and disk>pegs[j][-1]:return False
            pegs[j].append(disk)
        return pegs[dst]==list(range(n,0,-1))
    if name=='is_valid_parenthesization':
        depth=0
        for x in a:
            depth+=1 if x=='(' else -1
            if depth<0:return exact(False)
        return exact(depth==0)
    if name=='kth':return exact(sorted(a)[b])
    if name=='lcs_length':
        return exact(max(j-i for i in range(len(a)+1) for j in range(i,len(a)+1) if a[i:j] in b))
    if name=='lis':
        return exact(max(len(z) for z in sublists(a) if z==sorted(z)))
    if name=='longest_common_subsequence':
        opt=max(len(z) for z in sublists(a) if subseq(z,b))
        return isinstance(v,str) and len(v)==opt and subseq(v,a) and subseq(v,b)
    if name=='max_sublist_sum':return exact(max(sum(a[i:j]) for i in range(len(a)+1) for j in range(i,len(a)+1)))
    if name=='next_palindrome':
        n=int(''.join(map(str,a)))+1
        while str(n)!=str(n)[::-1]:n+=1
        return ints(v) and v==list(map(int,str(n)))
    if name=='next_permutation':
        seq=sorted(itertools.permutations(a));return ints(v) and tuple(v)==seq[seq.index(tuple(a))+1]
    if name=='pascal':return exact([[math.comb(i,j) for j in range(i+1)] for i in range(a)])
    if name=='possible_change':
        ways=[1]+[0]*b
        for coin in a:
            for total in range(coin,b+1):ways[total]+=ways[total-coin]
        return exact(ways[-1])
    if name in ('powerset','subsequences'):
        rows=sublists(a) if name=='powerset' else itertools.combinations(range(a,b),args[2])
        if not isinstance(v,list) or not all(ints(xs) for xs in v):return False
        # The specification treats powerset subsets as sets and each subsequence as ordered.
        canon=lambda xs:tuple(sorted(xs)) if name=='powerset' else tuple(xs)
        return collections.Counter(map(canon,v))==collections.Counter(map(canon,rows))
    if name=='rpn_eval':
        f={'+':operator.add,'-':operator.sub,'/':operator.truediv,'*':operator.mul};stack=[]
        for tok in a:
            if type(tok) is float:stack.append(tok)
            else:
                y=stack.pop();x=stack.pop();stack.append(f[tok](x,y))
        return type(v) in (float,int) and math.isclose(v,stack[0],rel_tol=1e-10,abs_tol=1e-10)
    if name=='shunting_yard':
        operators={ast.Add:'+',ast.Sub:'-',ast.Mult:'*',ast.Div:'/'}
        def postfix(x):
            if isinstance(x,ast.Constant):return [x.value]
            return postfix(x.left)+postfix(x.right)+[operators[type(x.op)]]
        return exact(postfix(ast.parse(' '.join(map(str,a)),mode='eval').body))
    if name=='sieve':return ints(v) and v==[i for i in range(2,a+1) if prime(i)]
    if name=='sqrt':return type(v) in (float,int) and math.isfinite(v) and abs(v-math.sqrt(a))<=b
    if name=='to_base':
        if not isinstance(v,str) or not v or not all(c in (string.digits+string.ascii_uppercase)[:b] for c in v):return False
        return not v.startswith('0') and int(v,b)==a
    if name=='wrap':
        if not isinstance(v,list) or not all(isinstance(x,str) and 0<len(x)<=b for x in v) or ''.join(v)!=a:return False
        # All generated words fit. A legal boundary has a space to its left or right.
        return all(l[-1]==' ' or r[0]==' ' for l,r in zip(v,v[1:]))
    raise KeyError(name)
