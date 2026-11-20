"""Consume only visible previous method bodies and the next method's public contract."""
from collections import Counter, defaultdict
from functools import lru_cache
import ast,math,re
from tokenizers import Tokenizer
from common import D,ROOT,sha,read,save
TOK=Tokenizer.from_file(str(ROOT/"work/memory_session5/packets/qwen_tokenizer.json"))
@lru_cache(maxsize=10000)
def ntoks(s):return len(TOK.encode(s,add_special_tokens=False).ids)
STOP=set("self the of to a provided function class method that and or in it which is this for from def none return object attribute param true false if else not list dict str int bool float given example".split())
def words(s):
    seq=re.findall(r"[A-Za-z][A-Za-z_0-9]+",s.lower())
    return [k for t in seq for k in [t,*t.split("_")] if k not in STOP and len(k)>1]
def lexical(docs,q):
    counts=[Counter(words(s)) for s in docs];freq=Counter(k for c in counts for k in c);N=len(docs);av=sum(sum(c.values()) for c in counts)/N if N else 1
    query=set(words(q));return [sum(math.log(1+(N-freq[t]+.5)/(freq[t]+.5))*c[t]*2.2/(c[t]+1.2*(.25+.75*sum(c.values())/max(1,av))) for t in query if c[t]) for c in counts]
def get_atoms(past):
    atoms=[];siblings=[]
    for j,p in enumerate(past):
        src=p["src"];f=ast.parse(src).body[0];lines=src.splitlines()
        fpos=min((b.lineno for b in f.body),default=len(lines)+1)
        body=[(k+1,line.strip()) for k,line in enumerate(lines) if k+1>=fpos and line.strip()]
        start=len(atoms); mapping={ln:start+n for n,(ln,_) in enumerate(body)}
        for ln,s in body:
            atoms.append({"method":j,"name":p["method"],"ln":ln,"s":s,"fields":set(re.findall(r"\bself\.(\w+)",s)),"write":False,"parents":set()})
        latest={}
        for n in sorted((x for x in ast.walk(f) if isinstance(x,ast.stmt) and x is not f),key=lambda x:x.lineno):
            if n.lineno not in mapping:continue
            i=mapping[n.lineno]; a=atoms[i]
            expr=[node for node in ast.walk(n) if getattr(node,"lineno",None)==n.lineno]
            loaded={x.id for x in expr if isinstance(x,ast.Name) and isinstance(x.ctx,ast.Load)}
            a["parents"].update(latest[x] for x in loaded if x in latest and latest[x]!=i)
            if isinstance(n,(ast.Assign,ast.AnnAssign,ast.AugAssign,ast.Delete)):
                lhs=n.targets if hasattr(n,"targets") else [n.target]
                a["write"]=any(any(isinstance(x,ast.Attribute) and isinstance(x.value,ast.Name) and x.value.id=="self" for x in ast.walk(target)) for target in lhs)
            if any(isinstance(x,ast.Attribute) and x.attr in {"append","extend","add","pop","remove","update","setdefault","discard","clear","insert"} for x in expr) and a["fields"]:a["write"]=True
            for x in expr:
                if isinstance(x,ast.Name) and isinstance(x.ctx,ast.Store):latest[x.id]=i
            if isinstance(n,(ast.If,ast.For,ast.While,ast.With,ast.Try)):
                for child in [*getattr(n,"body",[]),*getattr(n,"orelse",[])]:
                    if child.lineno in mapping:atoms[mapping[child.lineno]]["parents"].add(i)
        siblings.append(list(range(start,len(atoms))))
    return atoms,siblings
def render(selected,atoms):
    lines=[];last=None
    for i in sorted(selected):
        a=atoms[i]
        if a["method"]!=last:lines.append("["+a["name"]+"]");last=a["method"]
        lines.append(a["s"])
    return "\n".join(lines)
def fit_order(rank,atoms,budget):
    out=[]
    for i in rank:
        if ntoks(render(out+[i],atoms))<=budget:out.append(i)
    return render(out,atoms)
def memories(row):
    atoms,siblings=get_atoms(row["previous"]);query=row["name"]+" "+row["desc"]
    idx=list(range(len(atoms))); tokens=set(words(query))
    score=lexical([a["name"]+" "+a["s"] for a in atoms],query)
    method_scores=lexical([r["src"] for r in row["previous"]],query)
    fvals=defaultdict(float)
    for i,a in enumerate(atoms):
        for f in a["fields"]:fvals[f]=max(fvals[f],score[i]+2.*len(set(words(f))&tokens))
    extra=[]
    children=defaultdict(list)
    for i,a in enumerate(atoms):
        for k in a["parents"]:children[k].append(i)
    for i,a in enumerate(atoms):
        adjacent=[*a["parents"],*children[i]]
        support=max((score[j] for j in adjacent),default=0)
        field=max((fvals[f] for f in a["fields"]),default=0)
        bonus=.7*support+.55*field*(1.7 if a["write"] else .6)+1.5*int(a["write"])+.35*bool(a["fields"])
        extra.append(bonus)
    placebo=extra[:]
    for group in siblings:
        order=sorted(group,key=lambda i:sha("edge|"+row["id"]+"|"+str(i)))
        for i,j in zip(group,order):placebo[i]=extra[j]
    rank=lambda s:sorted(idx,key=lambda i:(-s[i],-atoms[i]["method"],i))
    methods=sorted(range(len(siblings)),key=lambda j:(-method_scores[j],-j))
    orders={"bm25_method":[i for j in methods for i in siblings[j]],"bm25_line":rank(score),"graph":rank([s+b for s,b in zip(score,extra)]),"placebo":rank([s+b for s,b in zip(score,placebo)]),"full":[i for g in siblings for i in g]}
    return {"none":"",**{k:fit_order(v,atoms,800 if k=="full" else 160) for k,v in orders.items()}}
def prompt(r,mem):
    constructor=r["constructor"].strip();defs="\n".join(r["interfaces"])
    return ("Class: "+r["cls"]+"\n"+r["summary"]+"\nAvailable imports: "+", ".join(r["imports"])+"\nConstructor:\n"+constructor+
            "\nClass method signatures:\n"+defs+"\nObserved lines from previously implemented methods (source order, indentation omitted):\n"+
            (mem if mem else "(empty)")+"\nImplement the following target method:\n"+r["desc"])
def main():
    out=[]
    for r in read(D/"visible.json"):
        mem=memories(r);out.append({"id":r["id"],"mem":mem,"tokens":{a:ntoks(s) for a,s in mem.items()}})
    save(D/"packets.json",out)
    print("tasks",len(out),"unique inputs",sum(len(set(r["mem"].values())) for r in out))
if __name__=="__main__":main()
