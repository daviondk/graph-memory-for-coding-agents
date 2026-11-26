"""Recover test-observation episodes from first-parent changes, before the selected target revision."""
import io
import subprocess
import zipfile
from functools import lru_cache
from study import *

def test_path(p):
    name=p.rsplit("/",1)[-1]
    return ("tests/" in p or p.startswith("tests/")) and (name.startswith("test_") or name.endswith("_tests.py")) and p.endswith(".py")

def get_history(repo,rev):
    # Exclude the target commit itself when the latest prior transition is observed.
    chain=git(repo,"rev-list","--first-parent","-n","194",rev).decode().splitlines()[1:]
    ordered=chain[:-1][::-1];parents=dict(zip(chain,chain[1:]))
    inp="".join(f"{sha} {parents[sha]}\n" for sha in ordered).encode()
    raw=git(repo,"diff-tree","--stdin","-r","--always","--no-renames","-m","--raw","-z","--no-abbrev",input=inp)
    stream=iter(raw.rstrip(b"\0").split(b"\0"))
    known=set(ordered);groups={}
    for token in stream:
        text=token.decode("ascii")
        if text in known:
            cur=text;groups[cur]=[]
        else:
            assert text.startswith(":")
            _,_,left,right,status=text.split()
            path=next(stream).decode("utf8","surrogateescape")
            groups[cur].append((left,right,status,path))
    assert list(groups)==ordered
    episodes=[];files_touched=[]
    process=subprocess.Popen(["git","-C",str(RAW/repo.replace("/","__")),"cat-file","--batch"],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    @lru_cache(maxsize=64)
    def tests(oid):
        if set(oid)=={"0"}:return {}
        process.stdin.write((oid+"\n").encode());process.stdin.flush()
        head=process.stdout.readline().split();assert head[0].decode()==oid and head[1]==b"blob"
        blob=process.stdout.read(int(head[2]));assert process.stdout.read(1)==b"\n"
        try:tree=ast.parse(blob)
        except (SyntaxError,UnicodeError,ValueError):return {}
        result={}
        top=[("",n) for n in tree.body if isinstance(n,ast.FunctionDef)]
        top.extend((cl.name+".",n) for cl in tree.body if isinstance(cl,ast.ClassDef)
                   for n in cl.body if isinstance(n,ast.FunctionDef))
        for prefix,node in top:
            if not node.name.startswith("test"):continue
            if node.body and isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Constant) and isinstance(node.body[0].value.value,str):
                node.body=node.body[1:]
            # Do not show fixtures/decorator parameter sets outside the captured method body.
            node.decorator_list=[]
            txt=ast.unparse(node)
            if not node.body or len(txt)>7800 or RISK.search(txt):continue
            result[prefix+node.name]=txt
        return result
    try:
        for i,sha in enumerate(ordered):
            diffs=groups[sha]
            sources=sorted(set(p for _,_,_,p in diffs)&target_modules(repo))
            files_touched.append(sources)
            for old,new,status,path in diffs:
                if not test_path(path) or status=="D":continue
                before=tests(old)
                for name,txt in tests(new).items():
                    if before.get(name)!=txt:
                        episodes.append(dict(i=i,sha=sha,path=path,address=name,anchors=sources,
                                             text=txt[:2200],full_digest=digest(txt.encode())))
    finally:
        process.stdin.close();process.stdout.close();process.wait()
    return dict(commits=ordered,boundary=chain[-1],files_touched=files_touched,episodes=episodes)

def package(repo,head,pkg):
    available=git(repo,"ls-tree","-r","--name-only",head,pkg+"/").decode().splitlines()
    out=io.BytesIO();sources={}
    with zipfile.ZipFile(out,"w") as z:
        for p in available:
            if not p.endswith(".py") or test_path(p):continue
            src=git(repo,"show",head+":"+p)
            desc=zipfile.ZipInfo(p,date_time=(1980,1,1,0,0,0))
            desc.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(desc,src)
            if p in target_modules(repo):sources[p]=src
    (RAW/(repo.replace("/","__")+".zip")).write_bytes(out.getvalue())
    return sources,digest(out.getvalue())

def extract_targets(repo,sources):
    tasks={};oracle={}
    for path,src in sorted(sources.items()):
        for node in ast.parse(src).body:
            if not isinstance(node,ast.FunctionDef) or node.name.startswith("_") or node.decorator_list:continue
            doc=ast.get_docstring(node)
            if not doc or ">>>" not in doc or FORBID_TARGET.search(node.name):continue
            desc=doc.split(">>>",1)[0].strip()
            if not desc or RISK.search(desc) or FORBID_TARGET.search(desc):continue
            if not (examples:=target_examples(doc,node.name)):continue
            sig=f"def {node.name}({ast.unparse(node.args)})"
            if node.returns:sig+=" -> "+ast.unparse(node.returns)
            question=sig+":\n"+desc[:1300]
            q=repo+"|"+path+"|"+node.name
            tasks[q]=dict(repo=repo,path=path,name=node.name,question=question)
            oracle[q]=dict(examples=[e.source for e in examples],n=len(examples))
    return tasks,oracle

def main():
    tasks={};oracles={};inputs={};pins={}
    for repo,(head,pkg,_) in SPECS.items():
        assert git(repo,"rev-parse",head).decode().strip()==head
        hist=get_history(repo,head)
        sources,blob=package(repo,head,pkg)
        subset,checks=extract_targets(repo,sources)
        oracles.update(checks);tasks.update(subset);inputs[repo]=hist
        pins[repo]=dict(head=head,package_sha=blob,n=len(hist["commits"]),episodes=len(hist["episodes"]),
                        potential=len(subset),boundary=hist["boundary"])
    write("history.json.gz",inputs);write("candidates.json.gz",tasks)
    write("pins.json",pins)
    (RAW/"author-inputs.json").write_text(json.dumps(oracles),encoding="utf8")
    print(pins)
if __name__=="__main__":
    main()
