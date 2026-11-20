"""Cross-check each inferred working directory against prior real observations and the old commit."""
import functools, gzip, json, posixpath, re, shlex
from pathlib import PurePosixPath
from extract import D,V,get,gz,pairs,source,scope,h
from objects import git
@functools.lru_cache(maxsize=160)
def allfiles(repo,rev):
    b=git(repo,"ls-tree","-r","-z",rev).stdout;paths={}
    for line in b.split(b"\0"):
        if line:
            head,k=line.split(b"\t",1);mode,kind,oid=head.decode().split()
            if mode in ("100644","100755") and kind=="blob":paths[k.decode("utf8","surrogateescape")]=oid
    return paths
def inspect_command(cmd,repo):
    default="/testbed";cmd=cmd.strip();lead=re.match(r"^cd\s+(['\"]?)([A-Za-z0-9_./-]+)\1\s*&&\s*(.*)$",cmd,re.S)
    if lead:default=posixpath.normpath(posixpath.join(default,lead[2]));cmd=lead[3]
    cmd=re.sub(r"\s*\|\s*head(?:\s+(?:-\d+|-n\s+\d+))?\s*$","",cmd)
    if re.search(r"[;\x60$|><&\n]",cmd):return []
    try:t=shlex.split(cmd)
    except ValueError:return []
    if not t:return []
    if t[0]=="ls":
        paths=[x for x in t[1:] if not x.startswith("-")]
        if len(paths)>1:return []
        rr,p=scope(paths[0] if paths else ".",default,source(repo));return [(rr,p,"ls")] if rr else []
    if t[0] not in ("cat","sed","head","tail","nl","rg","grep"):return []
    rr,p=scope(t[-1],default,source(repo))
    if not rr or not p.endswith((".py",".rst",".toml",".md",".txt",".cfg",".yml",".yaml",".cpp",".h")):return []
    return [(rr,p,"content")]
@functools.lru_cache(maxsize=400)
def content(repo,oid):return set(l.strip() for l in git(repo,"cat-file","blob",oid).stdout.decode("utf8",errors="replace").splitlines() if len(l.strip())>=20)
def witness(note,steps,pair):
    root=note["key"]["root"];ps=allfiles(note["repo"],pair["parent"])
    for step,cmd,row in reversed(steps):
        if step>=note["step"] or row.get("extra",{}).get("returncode")!=0:continue
        raw=row.get("extra",{}).get("raw_output")
        if not isinstance(raw,str) or not raw.strip():continue
        for rr,p,kind in inspect_command(cmd,note["repo"]):
            if rr!=root:continue
            if kind=="ls":
                # Match distinct entries of the exact logged directory to its archived tree.
                sub=p+"/" if p!="." else "";expected={s[len(sub):].partition("/")[0] for s in ps if s.startswith(sub)}
                displayed=set()
                for ln in raw.splitlines()[:180]:
                    pure=ln.strip().rstrip("/")
                    if pure and " " not in pure:displayed.add(pure)
                    elif re.match(r"^[-dl][rwxstST-]{9}\s",pure):displayed.add(pure.split()[-1].rstrip("/"))
                shared=sorted(expected&displayed)
                if len(shared)>=3:return {"support":"directory_names","witness_step":step,"scope":p,"matched":[h(s.encode())[:16] for s in shared[:5]]}
            elif p in ps:
                lines=content(note["repo"],ps[p]);shown={re.sub(r"^\s*\d+[:\t ]","",l).strip() for l in raw.splitlines()[:180] if len(l.strip())>=20}
                shared=sorted(shown&lines)
                if len(shared)>=2:return {"support":"tracked_file_lines","witness_step":step,"scope":p,"matched":[h(s.encode())[:16] for s in shared[:4]]}
    return {"support":"no_prior_root_witness"}
if __name__=='__main__':
    roster={r['iid']:r for r in get(D/'roster.json')};meta={r['iid']:r for r in get(D/'revision_pairs.json')};keys=get(D/'keys.json');observed={}
    for note in keys:
        iid=note['iid']
        if iid not in observed:observed[iid]=list(pairs(get(V/'benchmark'/roster[iid]['file'])['messages']))
    checked=[{**note,**witness(note,observed[note['iid']],meta[note['iid']])} for note in keys]
    gz('provenance.json.gz',checked)
    import collections;print(collections.Counter(v['support'] for v in checked))
