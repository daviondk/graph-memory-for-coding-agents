"""Use immutable before/after raw files, pre-filter metadata; persist safe structural diffs only."""
from collections import defaultdict, Counter
import concurrent.futures
import html
import requests
import time
from urllib.parse import quote
from common import *

def location(project):
    return "eclipse-jgit/jgit" if project=="eclipse/jgit" else project

def get(url):
    for attempt in range(3):
        try:
            r=requests.get(url,timeout=(12,55),headers={"User-Agent":"graph-memory-public-research/1"})
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            if attempt==2:raise
            time.sleep(1+attempt)

def changes(block):
    """Convert contextual Git hunks into maximal runs of modified lines."""
    hunks=[]
    lo=new=at_old=at_new=None
    removed=added=0
    def flush():
        nonlocal removed,added
        if removed or added:
            hunks.append([at_old if removed else at_old-1,removed,at_new if added else at_new-1,added])
        removed=added=0
    for line in block.splitlines():
        m=re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@",line)
        if m:
            flush()
            a,na,b,nb=m.groups()
            lo=int(a)+(na=="0")
            new=int(b)+(nb=="0")
        elif lo is not None and line.startswith(" "):
            flush();lo+=1;new+=1
        elif lo is not None and line[:1] in ("-","+"):
            if not removed and not added:at_old,at_new=lo,new
            if line[0]=="-":lo+=1;removed+=1
            else:new+=1;added+=1
    flush()
    return hunks

def fetch_commit(batch):
    project,commit=batch[0]["project"],batch[0]["commit"]
    base=f"https://github.com/{location(project)}/commit/{commit}"
    try:
        doc=get(base).decode("utf8","replace")
        ps=re.findall(r'"parents"\s*:\s*\[([^\]]*)\]',doc)
        if not ps:return None,"missing_parent_metadata"
        parents=json.loads("["+ps[0]+"]")
        if len(parents)!=1:return None,"not_single_parent"
        parent=parents[0];assert re.fullmatch(r"[a-f0-9]{40}",parent)
        title=re.search(r"<title>(.*?)</title>",doc,re.S|re.I)
        if not title:return None,"missing_subject"
        subject=html.unescape(title[1]).strip()
        if UNSAFE.search(subject):return None,"excluded_subject"
        content=get(base+".diff")
        patch=content.decode("utf8","replace")
        files=[]
        for block in re.split(r"(?m)^diff --git ",patch)[1:]:
            first=block.splitlines()[0]
            fm=re.match("^a/(.*?) b/(.*)$",first)
            if not fm:continue
            old,dest=fm.groups()
            if UNSAFE.search(old) or UNSAFE.search(dest):continue
            if not old.endswith(".java") or not dest.endswith(".java"):continue
            pre=re.split(r"(?m)^@@ ",block,maxsplit=1)[0]
            if re.search(r"(?m)^new file mode ",pre):old=None
            if re.search(r"(?m)^deleted file mode ",pre):dest=None
            ix=re.search(r"(?m)^index ([a-f0-9]+)\.\.([a-f0-9]+)",pre)
            files.append(dict(old=old,new=dest,old_git=ix[1] if ix else None,new_git=ix[2] if ix else None,hunks=changes(block)))
        def select(q):
            names=q["source"][0].split(".");types={s for s in names if s[:1].isupper()}
            words={t.lower() for t in names}
            def order(f):
                path=f["old"] or f["new"]
                return (Path(path).stem not in types,-len(words&{a.lower() for a in re.split(r"[/.$]",path)}),path,f["new"] or "")
            return sorted(range(len(files)),key=lambda i:order(files[i]))[:8]
        look={q['case']:select(q) for q in batch}
        selected=sorted({idx for group in look.values() for idx in group})
        current={}
        for idx in selected:
            f=files[idx]
            current[str(idx)]=f
        return dict(project=project,commit=commit,parent=parent,sha256_diff=sha(content),java_frontier_size=len(files),
                    files=current,selected=look),None
    except Exception as ex:
        return None, f"{type(ex).__name__}: {str(ex)[:175]}"

def blob(item):
    project,rev,path,ref=item
    url=f"https://raw.githubusercontent.com/{location(project)}/{rev}/"+quote(path,safe="/")
    ident=sha(url.encode());p=CACHE/"raw"/ident
    try:
        if not p.is_file():
            data=get(url)
            atomic=CACHE/"raw"/(ident+".part")
            atomic.write_bytes(data);atomic.replace(p)
        data=p.read_bytes()
        g=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
        if ref and not g.startswith(ref):return dict(url=url,error="git-blob-hash-mismatch")
        return dict(url=url,cache=p.relative_to(CACHE).as_posix(),sha256=sha(data),git_blob=g,size=len(data))
    except Exception as ex:
        return dict(url=url,error=f"{type(ex).__name__}: {str(ex)[:175]}")

def main():
    check(read("selection.json")["files"])
    q=read("queries.json")
    batches=defaultdict(list)
    for x in q:batches[x["project"],x["commit"]].append(x)
    records={};errors={}
    with concurrent.futures.ThreadPoolExecutor(6) as workers:
        for key,(r,error) in zip(batches,workers.map(fetch_commit,batches.values())):
            if error:errors[key[1]]=error
            else:records[key[1]]=r
    (CACHE/"raw").mkdir(exist_ok=True)
    needed={}
    for r in records.values():
        for f in r["files"].values():
            for side,rev in [("new",r["commit"]),("old",r["parent"])]:
                path=f[side]
                if not path:continue
                key=(r["project"],rev,path,f[side+"_git"])
                needed[key]=None
    with concurrent.futures.ThreadPoolExecutor(8) as workers:
        for key,out in zip(needed,workers.map(blob,needed)):
            needed[key]=out
    for r in records.values():
        for f in r["files"].values():
            for side,rev in [("new",r["commit"]),("old",r["parent"])]:
                path=f[side]
                if path:f[side+"_blob"]=needed[r["project"],rev,path,f[side+"_git"]]
    save("sources.json.gz",records)
    save("acquisition.json",dict(errors=errors,commits=len(records),files=len(needed),failed_blobs=sum("error" in b for b in needed.values()),
                                  files_sha=hashfiles(["select_cases.py","PROTOCOL_RU.md","selection.json","acquire.py","sources.json.gz"])))
    print("commits",len(records),"errors",errors,"blobs",len(needed),"missing",sum("error" in b for b in needed.values()))
if __name__=="__main__":main()
