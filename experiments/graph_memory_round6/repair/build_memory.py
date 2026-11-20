"""Rank code the explorer has already read. This module never opens evaluation metadata."""
import ast,bisect,collections,gzip,hashlib,json,math,re,sys
from pathlib import Path
D=Path(__file__).resolve().parent
W=D.parent.parent
sys.path.insert(0,str(W/"graph_memory_round3/repo/lib"))
from tokenizers import Tokenizer
tokenizer=Tokenizer.from_file(str(W/"memory_session5/live/tokenizer.json"))
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def dump(p,x):
    b=json.dumps(x,ensure_ascii=False,sort_keys=True).encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def tokens(s):return tokenizer.encode(s,add_special_tokens=False).ids
STOP=set("self cls class def from import true false none this that with have should would which error file line python sympy function return print the and for not but can are when use has will what how does was like then see code one into example following than using gives from about also same expected method".split())
def terms(s):
    words=re.findall(r"[A-Za-z_][A-Za-z_0-9]*",s)
    return {x.lower() for w in words for x in [w,*re.findall(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+",w)] if len(x)>=3 and x.lower() not in STOP}
def main(i):
    dest=D/"tasks"/i;root=dest/"base";issue=json.loads((dest/"public.json").read_text(encoding="utf8"))["problem_statement"]
    issue=tokenizer.decode(tokens(issue)[:850]); q=terms(issue)
    focus=terms(" ".join(re.findall(r"\b([A-Za-z_]\w*)\s*\(|\bnevermatch",issue))+" "+" ".join(re.findall(r"\x60([A-Za-z_.]\w*)\x60",issue)))
    explicit={p.replace("\\","/") for p in re.findall(r"sympy[/\\][A-Za-z_0-9/\\]+\.py",issue)}
    pool=[]
    for p in sorted((root/"sympy").rglob("*.py")):
        if any(t in {"tests","testing","benchmarks"} for t in p.parts) or p.name.startswith("test_") or p.name=="__init__.py":continue
        s=p.read_text(encoding="utf8",errors="replace"); path=p.relative_to(root).as_posix()
        defs=set(re.findall(r"(?m)^\s*(?:def|class)\s+(\w+)",s));matches={n.lower() for n in defs}&q
        score=10*int(path in explicit)+2.8*len(matches&focus)+1.3*len(matches)+2*len(q&terms(p.stem))+.6*len(q&terms(path))
        if score:pool.append((score,path))
    paths=[p for _,p in sorted(pool,key=lambda x:(-x[0],x[1]))[:8]]
    nodes=[];files={};name_to=collections.defaultdict(list)
    for p in paths:
        lines=(root/p).read_text(encoding="utf8",errors="replace").splitlines()
        files[p]=lines
        try:tree=ast.parse("\n".join(lines))
        except (ValueError,SyntaxError):continue
        def walk(body,parent=""):
            for x in body:
                if not isinstance(x,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):continue
                if isinstance(x,ast.ClassDef):walk(x.body,x.name);continue
                start=x.lineno; end=x.end_lineno
                ref={f.func.attr if isinstance(f.func,ast.Attribute) else f.func.id for f in ast.walk(x) if isinstance(f,ast.Call) and isinstance(f.func,(ast.Attribute,ast.Name))}
                j=len(nodes);name_to[x.name].append(j)
                nodes.append(dict(p=p,fn=x.name,cl=parent,start=start,end=end,ref=sorted(ref)))
        walk(tree.body)
    chunks=[];byterm=collections.Counter();n=len(nodes)
    for j,u in enumerate(nodes):
        for st in range(u["start"],u["end"]+1,14):
            en=min(st+13,u["end"]);s="\n".join(files[u["p"]][st-1:en]);v=terms(s);byterm.update(v)
            chunks.append(dict(j=j,st=st,en=en,text=s,v=v))
    def weight(v):return sum(math.log1p((len(chunks)+1)/(byterm[t]+1)) for t in v)
    top=[0.]*n
    for c in chunks:
        u=nodes[c["j"]];name=terms(u["fn"]+" "+u["cl"])
        common=q&c["v"]; score=weight(common)/math.sqrt(max(7,len(c["v"])))+.90*weight(name&q)+.8*weight(name&focus)+.4*weight(terms(u["p"])&q)+.25*weight(common&focus)
        c["sc"]=score;top[c["j"]]=max(top[c["j"]],score)
    edges=set(); groups=collections.defaultdict(list)
    for j,u in enumerate(nodes):
        if u["cl"]:groups[u["p"],u["cl"]].append(j)
        for ref in u["ref"]:
            dsts=name_to.get(ref,[])
            same=[k for k in dsts if nodes[k]["p"]==u["p"]]
            for k in same or (dsts if len(dsts)==1 else []):
                if k!=j:edges.add((j,k))
    for group in groups.values():
        for x,y in zip(group,group[1:]):edges.add((x,y));edges.add((y,x))
    mapping=sorted(range(n),key=lambda j:sha(i+"|edge|"+str(j)))
    def propagated(edges):
        deg=collections.Counter(x for x,y in edges); back=collections.Counter(y for x,y in edges);a=[0.]*n
        for x,y in edges:a[y]=max(a[y],top[x]/math.sqrt(max(1,deg[x])*max(1,back[y])));a[x]=max(a[x],.5*top[y]/math.sqrt(max(1,back[y])*max(1,deg[x])))
        return a
    graph=propagated(edges);shuf=propagated({(mapping[x],mapping[y]) for x,y in edges})
    packets={};kept={}
    for arm,extra in [("flat",[0.]*n),("graph",graph),("shuffled",shuf)]:
        ranked=sorted(chunks,key=lambda c:(-(c["sc"]+.85*extra[c["j"]]),nodes[c["j"]]["p"],c["st"]))
        chosen=[];records=[];used=0
        for c in ranked:
            u=nodes[c["j"]];record=f'{u["p"]}  L{c["st"]}-{c["en"]}  {u["cl"]}.{u["fn"]}\n'+c["text"]
            size=len(tokens(record))+2
            if used+size>1800:continue
            records.append(record);chosen.append([u["p"],c["st"],c["en"]]);used+=size
            if used>1770:break
        packet="\n\n".join(records)
        while len(tokens(packet))>1800:
            records.pop();chosen.pop();packet="\n\n".join(records)
        packets[arm]=packet;kept[arm]=chosen
    dump(dest/"packets.json.gz",{"issue":issue,"packets":packets,"paths":paths,"kept":kept,"edges":len(edges),"nodes":n,"blocks":len(chunks),"tokens":{k:len(tokens(v)) for k,v in packets.items()}})
if __name__=="__main__":
    ids=json.loads((D/"cohort.json").read_text())["ids"]
    for i in ids:main(i);print(i,flush=True)

