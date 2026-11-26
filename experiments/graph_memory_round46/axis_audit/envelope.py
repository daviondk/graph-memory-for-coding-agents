import functools

LOW, HIGH = -4, 4

def make_envelope(solve):
    solve=functools.lru_cache(None)(solve)
    spans=[]
    def append(a,b,answer):
        if spans and spans[-1][2]==answer and spans[-1][1]==a-1:
            spans[-1]=(spans[-1][0],b,answer)
        else:
            spans.append((a,b,answer))
    def visit(a,b):
        left,v0,k0=solve(a)
        right,v1,k1=solve(b)
        if left==right:
            append(a,b,left)
            return
        assert a<b and k0<k1
        if a+1==b:
            append(a,a,left)
            append(b,b,right)
            return
        middle=min(b-1,max(a,(v0-v1)//(k1-k0)))
        visit(a,middle)
        visit(middle+1,b)
    visit(LOW,HIGH)
    assert spans[0][0]==LOW and spans[-1][1]==HIGH
    return spans,solve.cache_info().misses
