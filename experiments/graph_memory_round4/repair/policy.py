"""Streaming maximum coverage over candidate repair witnesses; at most two records survive a write."""
import ast,copy,itertools
from base import sha,stable

POLICIES=("empty","recent","failed","individual","union","all")
BUDGET=384
def mutations(source,name):
    tree=ast.parse(source)
    original=ast.unparse(tree)
    proposals={}
    comparisons={ast.Lt:(ast.LtE,ast.Gt),ast.LtE:(ast.Lt,ast.GtE),ast.Gt:(ast.GtE,ast.Lt),ast.GtE:(ast.Gt,ast.LtE),ast.Eq:(ast.NotEq,),ast.NotEq:(ast.Eq,),ast.In:(ast.NotIn,),ast.NotIn:(ast.In,)}
    binary={ast.Add:(ast.Sub,),ast.Sub:(ast.Add,),ast.Mult:(ast.Add,),ast.Div:(ast.FloorDiv,),ast.FloorDiv:(ast.Div,),ast.Mod:(ast.FloorDiv,)}
    for i,n in enumerate(ast.walk(tree)):
        alternatives=[]
        if isinstance(n,ast.Compare) and len(n.ops)==1:alternatives=[("ops",[x()]) for x in comparisons.get(type(n.ops[0]),[])]
        elif isinstance(n,ast.BinOp):alternatives=[("op",x()) for x in binary.get(type(n.op),[])]
        elif isinstance(n,ast.BoolOp):alternatives=[("op",ast.Or() if isinstance(n.op,ast.And) else ast.And())]
        elif isinstance(n,ast.Constant) and type(n.value) is int and abs(n.value)<=2:alternatives=[("value",v) for v in (n.value-1,n.value+1)]
        elif isinstance(n,ast.Constant) and type(n.value) is bool:alternatives=[("value",not n.value)]
        elif isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in {"max","min","all","any"}:
            alternatives=[("func",ast.Name({"max":"min","min":"max","all":"any","any":"all"}[n.func.id],ast.Load()))]
        elif isinstance(n,ast.If):alternatives=[("test",ast.UnaryOp(ast.Not(),copy.deepcopy(n.test)))]
        for field,value in alternatives:
            trial=copy.deepcopy(tree)
            setattr(list(ast.walk(trial))[i],field,value)
            code=ast.unparse(ast.fix_missing_locations(trial))
            if code!=original:proposals[code]=[i,field]
    return [original]+sorted(proposals,key=lambda code:sha("r4mutation|"+name+"|"+code))[:24]
def bytes_used(records):
    return len(stable(records).encode())
def write(records,item,arm,weight):
    if arm=="empty":return []
    pool=records+[item]
    if arm=="all":return pool
    def rank(xs):
        recent=tuple(sorted((x[0] for x in xs),reverse=True))
        if arm=="recent":return (len(xs),recent)
        if arm=="failed":return (sum(x[2]&1 for x in xs),len(xs),recent)
        def w(mask):return mask.bit_count()+(weight-1)*(mask&1)
        merged=0
        for x in xs:merged|=x[2]
        value=w(merged) if arm=="union" else sum(w(x[2]) for x in xs)
        return (value,len(xs),recent)
    options=[list(xs) for k in range(min(len(pool),2)+1) for xs in itertools.combinations(pool,k) if bytes_used(xs)<=BUDGET]
    return max(options,key=rank)
def pretty(xs):
    return "\n".join(("FAIL " if mask&1 else "PASS ")+statement for _,statement,mask in xs) or "(no saved test observations)"

