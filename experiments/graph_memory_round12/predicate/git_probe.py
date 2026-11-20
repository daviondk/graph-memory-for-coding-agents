"""Measure validity of cached empty fixed-string searches on complete tree transitions."""
import collections,difflib,gzip,hashlib,itertools,json,os,random,subprocess,tempfile,time
from pathlib import Path
D=Path(__file__).resolve().parent
SCOPES=("","src","docs")
LITERALS=("alpha","BETA","+++","[n]","green tea","NoSuchThing")
def save(name,x):
    data=(json.dumps(x,ensure_ascii=False,indent=None if name.endswith(".gz") else 2,sort_keys=True)+"\n").encode()
    (D/name).write_bytes(gzip.compress(data,mtime=0) if name.endswith(".gz") else data)
def inside(path,scope):return not scope or path==scope or path.startswith(scope+"/")
def applicable(pattern,kind="fixed",observed_exit=1,complete=True):
    return kind=="fixed" and observed_exit==1 and complete and bool(pattern) and "\n" not in pattern and "\x00" not in pattern
def contains(lines,pat):return any(pat in s for s in lines)
def only_added(a,b):
    result=[]
    for tag,_,__,i,j in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes():
        if tag in ("insert","replace"):result.extend(b[i:j])
    return result
def finite():
    vals=((),("a",),("b",),("a","b"),("ba","a"));paths=("src/q","docs/q")
    states=[dict(zip(paths,v)) for v in itertools.product(vals,repeat=2)]
    empty=flips=0
    for old,new in itertools.product(states, repeat=2):
        for s,k in itertools.product(SCOPES,("a","b","ba","x")):
            if any(inside(p,s) and contains(lines,k) for p,lines in old.items()):continue
            target=any(inside(p,s) and contains(lines,k) for p,lines in new.items())
            pred=any(inside(p,s) and contains(only_added(old[p],new[p]),k) for p in paths)
            assert pred==target;empty+=1;flips+=target
    return dict(states=len(states),transitions=len(states)**2,old_negative=empty,flips=flips)
class Git:
    def __init__(self,path):self.path=path
    def run(self,*args,inp=None,ok=(0,)):
        p=subprocess.run(["git",*args],cwd=self.path,input=inp,capture_output=True,
            env={**os.environ,"LC_ALL":"C","GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":os.devnull})
        if p.returncode not in ok:raise RuntimeError((args,p.returncode,p.stderr[:400]))
        return p.stdout,p.returncode
    def tree(self,files):
        nodes={}
        for p,(data,mode) in files.items():
            parent,name=p.split("/")
            blob=self.run("hash-object","-w","--stdin",inp=data)[0].strip().decode()
            nodes.setdefault(parent,[]).append(f"{mode} blob {blob}\t{name}".encode())
        refs=[]
        for parent,children in nodes.items():
            sub=self.run("mktree","-z",inp=b"\x00".join(children)+b"\x00")[0].strip().decode()
            refs.append(f"040000 tree {sub}\t{parent}".encode())
        return self.run("mktree","-z",inp=b"\x00".join(refs)+(b"\x00" if refs else b""))[0].strip().decode()
    def grep(self,tree,scope,k):
        pathspec=[":(top,literal)"+scope] if scope else []
        return self.run("grep","--threads=1","-F","-q","-e",k,tree,"--",*pathspec,ok=(0,1))[1]==0
    def pickaxe(self,a,b,scope,k):
        pathspec=[":(top,literal)"+scope] if scope else []
        return bool(self.run("diff","--text","--no-ext-diff","--no-textconv","--no-renames","--name-only","-z","-S"+k,a,b,"--",*pathspec)[0])
def parse_patch(raw):
    hunk=False;out=[]
    for s in raw.split(b"\n"):
        if s.startswith(b"@@ "):hunk=True
        elif hunk and s.startswith(b"+"):out.append(s[1:])
    return out
def delta(g,a,b):
    raw,_=g.run("diff","--raw","-r","-z","--no-abbrev","--no-renames",a,b)
    chunks=raw.split(b"\x00")[:-1];assert len(chunks)%2==0
    rows={};size=len(raw);calls=1;cache={}
    for header,path in zip(chunks[::2],chunks[1::2]):
        old,new,left,right,status=header[1:].decode().split()
        if new not in ("100644","100755","000000") or old not in ("100644","100755","000000"):raise ValueError("unsupported type")
        p=path.decode()
        if status=="D" or left==right:rows[p]=[];continue
        if (left,right) not in cache:
            if status=="A":
                blob=g.run("cat-file","blob",right)[0];lines=blob.split(b"\n")
            elif status=="M":
                blob=g.run("diff","--text","--no-ext-diff","--no-textconv","--unified=0",left,right)[0];lines=parse_patch(blob)
            else:raise ValueError(status)
            size+=len(blob);calls+=1;cache[left,right]=lines
        rows[p]=cache[left,right]
    return rows,size,calls
def schedule():
    case=0
    for i in range(8):
        literal=LITERALS[i%5].encode()
        base=b"header\nsame\nsame\nend\n";variant=base+literal+(b"\n" if i%2 else b"")
        for mode in ("create","delete","move_in","move_out","copy_in","modify","mode_only","unchanged"):
            a={"src/base.py":(base,"100644"),"docs/static.txt":(b"stable","100644")}
            if mode!="create":a["docs/sp ace.txt"]=(variant,"100644")
            b=a.copy()
            if mode=="create":b["src/plus.py"]=(variant,"100644")
            elif mode=="delete":del b["docs/sp ace.txt"]
            elif mode=="move_in":b["src/sp ace.txt"]=b.pop("docs/sp ace.txt")
            elif mode=="move_out":a["src/sp ace.txt"]=a.pop("docs/sp ace.txt")
            elif mode=="copy_in":b["src/copied file.py"]=a["docs/sp ace.txt"]
            elif mode=="modify":b["src/base.py"]=(b"header\nsame\n"+literal+b"\nsame\nend","100644")
            elif mode=="mode_only":b["src/base.py"]=(base,"100755")
            yield case,mode,a,b
            case+=1
def main():
    results=finite();rows=[];costs=[];times=collections.defaultdict(float)
    guard=[applicable(*x) for x in (("a",),("a","regex"),("x","fixed",2),("a","fixed",1,False),("",),("a\nb",),("\x00",))]
    assert guard==[True,False,False,False,False,False,False]
    with tempfile.TemporaryDirectory(prefix="r12-pred-",dir=D.parent.parent.parent/"outputs") as tmp:
        g=Git(tmp);g.run("init","-q")
        for case,mode,old,new in schedule():
            a=g.tree(old);b=g.tree(new)
            start=time.monotonic();ds,size,calls=delta(g,a,b);times["delta_once"]+=time.monotonic()-start
            rd=g.run("diff","--name-status","--find-renames=100%","-z",a,b)[0].split(b"\x00")
            moved=set()
            while rd and rd[0]:
                code=rd.pop(0).decode()
                if code.startswith("R"):rd.pop(0);moved.add(rd.pop(0).decode())
                else:rd.pop(0)
            costs.append(dict(case=case,kind=mode,old=a,new=b,delta_bytes=size,git_calls=calls))
            for scope,word in itertools.product(SCOPES,LITERALS):
                if g.grep(a,scope,word):continue
                start=time.monotonic();target=g.grep(b,scope,word);times["whole_grep_queries"]+=time.monotonic()-start
                start=time.monotonic();pick=g.pickaxe(a,b,scope,word);times["pickaxe_queries"]+=time.monotonic()-start
                k=word.encode();paths=[p for p in ds if inside(p,scope)]
                start=time.monotonic();pred=any(contains(ds[p],k) for p in paths);times["match_materialized"]+=time.monotonic()-start
                naive=any(p not in moved and contains(ds[p],k) for p in paths)
                full=any(inside(p,scope) and contains(data.split(b"\n"),k) for p,(data,_) in new.items())
                assert full==target
                rows.append(dict(case=case,kind=mode,scope=scope,word=word,target=target,delta=pred,native_pickaxe=pick,
                    rename_skipped=naive,path_guard=bool(paths),unchanged=False,full=full))
    save("rows.gz",rows);save("costs.json",costs)
    score={m:dict(triggered=sum(x[m] for x in rows),fp=sum(x[m] and not x["target"] for x in rows),
        fn=sum(not x[m] and x["target"] for x in rows)) for m in ("delta","native_pickaxe","rename_skipped","path_guard","unchanged","full")}
    save("results.json",dict(finite=results,controlled=len(rows),real_git_transitions=len(costs),distinct_pairs=len({(x["old"],x["new"]) for x in costs}),
      actual_flips=sum(x["target"] for x in rows),methods=score,guard_checks=guard,
      delta_bytes=sum(x["delta_bytes"] for x in costs),delta_git_calls=sum(x["git_calls"] for x in costs),timings_s=times))
if __name__=="__main__":main()
