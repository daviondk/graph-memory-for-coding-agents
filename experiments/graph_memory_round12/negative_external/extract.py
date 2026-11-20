"""Measure feasibility and freeze negative query keys from author-published mini-SWE-agent logs."""
import collections, gzip, hashlib, json, posixpath, re, shlex
from pathlib import Path
D=Path(__file__).resolve().parent
V=Path("D:/CodexResearch/x20-official-vibe/VibeMemBench")
H=V/"benchmark/history/python"
REPOSITORIES="alteryx/woodwork bashtage/arch codezonediitj/pydatastructs CS-SI/eodag fatiando/harmonica hdmf-dev/hdmf mpmath/mpmath NeurodataWithoutBorders/pynwb pandas-dev/pandas PennyLaneAI/pennylane pybamm-team/PyBaMM pyccel/pyccel pyqtgraph/pyqtgraph Qiskit/qiskit-terra sdv-dev/RDT stac-utils/pystac xgcm/xgcm".split()
BAD=re.compile(r"\b(vulnerability|vulnerabilities|exploit|SQL injection|XSS|CVE-\d+|remote code execution|path traversal)\b",re.I)
SEARCH=re.compile(r"(?:^|[;&|\n])\s*(?:git\s+)?(?:rg|grep)\b")
EXIT=re.compile(r"\A\s*<returncode>\s*(-?\d+)\s*</returncode>\s*<output>(.*?)</output>\s*\Z",re.S)
PATH=re.compile(r"[a-zA-Z0-9_./-]+")
def h(b):return hashlib.sha256(b).hexdigest()
def get(p):return json.loads(p.read_bytes())
def save(name,v):
    (D/name).write_text(json.dumps(v,ensure_ascii=True,indent=1),encoding="utf8")
def gz(name,v):
    (D/name).write_bytes(gzip.compress(json.dumps(v,separators=(",",":"),ensure_ascii=True).encode(),mtime=0))
def source(r):
    direct=r.split("/")[1]
    return ("/testbed/"+direct,"/"+direct,"/testbed")
def scope(path,cwd,roots):
    if not PATH.fullmatch(path):return None,None
    value=posixpath.normpath(posixpath.join(cwd,path))
    for root in roots:
        if value==root:return root,"."
        if value.startswith(root+"/"):return root,value[len(root)+1:]
    return None,None
def literal(s,mode):
    if not s or not s.isascii() or len(s)>180 or "\n" in s:return None
    if mode=="fixed":return s
    # Unescaped +?|(){} are literals in GNU basic grep. With -E or ripgrep they are operators.
    special=set(".^$[]*")
    extended=set("()+?{}|")
    result=[];i=0
    while i<len(s):
        c=s[i];i+=1
        if c=="\\":
            if i==len(s):return None
            n=s[i];i+=1
            if n in special or n=="\\" or (mode=="extended" and n in extended):result.append(n)
            else:return None
        elif c in special or (mode=="extended" and c in extended):return None
        else:result.append(c)
    return "".join(result)
def parse(cmd,default,roots):
    cmd=cmd.strip();cwd=default
    lead=re.match(r"^cd\s+(['\"]?)([A-Za-z0-9_./-]+)\1\s*&&\s*(.*)$",cmd,re.S)
    if lead:
        cwd=posixpath.normpath(posixpath.join(default,lead[2]));cmd=lead[3]
    if not re.match(r"^(?:git\s+)?(?:grep|rg)\b",cmd):return None,"compound_prefix"
    if re.search(r"[\x00\n\r;|\x60$<>]",cmd) or '&&' in cmd:return None,"pipe_branch_expansion_or_redirect"
    try:t=shlex.split(cmd,posix=True)
    except ValueError:return None,"malformed"
    if t[:2]==["git","grep"]:tool="git-grep";t=t[2:]
    elif t and t[0] in ("grep","rg"):tool=t.pop(0)
    else:return None,"other"
    mode="basic" if tool!="rg" else "extended";fold=False;word=False;recurse=tool!="grep";inc=[];pos=[];i=0
    while i<len(t):
        a=t[i];i+=1
        if a=="--":continue
        if a in ("-A","-B","-C","-m"):
            if i==len(t) or not t[i].isdigit():return None,"bad_context_arg"
            i+=1;continue
        if a.startswith("--include="):inc.append(a.partition("=")[2]);continue
        if a in ("--include","-g","--glob"):
            if i==len(t):return None,"missing_glob"
            inc.append(t[i]);i+=1;continue
        if a in ("--ignore-case","--fixed-strings","--word-regexp","--recursive","--line-number","--no-heading","--color=never","--with-filename"):
            if a=="--ignore-case":fold=True
            if a=="--fixed-strings":mode="fixed"
            if a=="--word-regexp":word=True
            if a=="--recursive":recurse=True
            continue
        if a=="-e":
            if i==len(t) or pos:return None,"multiple_patterns"
            pos.append(t[i]);i+=1;continue
        if a.startswith("-"):
            if re.fullmatch(r"-[ABCm]\d+",a):continue
            flags=a[1:]
            if not re.fullmatch("[rRFinwhlHIE]+",flags):return None,"unsupported_flag"
            if 'F' in flags:mode='fixed'
            if 'E' in flags:mode='extended'
            fold|="i" in flags;word|="w" in flags;recurse|=bool(set(flags)&set("rR"))
            continue
        pos.append(a)
    if len(pos) not in (1,2) or len(pos)==1 and not recurse:return None,"missing_multiple_or_stdin_scope"
    raw=literal(pos[0],mode)
    if not raw:return None,"regex_or_multiline"
    if len(raw)<2:return None,"short_literal"
    if any(not re.fullmatch(r"\*\.[A-Za-z0-9_]+",g) for g in inc):return None,"glob_outside_grammar"
    root,path=scope(pos[-1] if len(pos)==2 else ".",cwd,roots)
    if path is None:return None,"outside_named_root_or_dynamic_path"
    return dict(literal=raw,scope=path,oi=fold,word=word,globs=sorted(inc),recurse=recurse,tool=tool,root=root),None
def pairs(msgs):
    byid={}
    for i,m in enumerate(msgs):
        if m.get("role")=="assistant":
            for tc in m.get("tool_calls") or []:
                fn=tc.get('function',{});f=fn.get("arguments")
                try:arg=json.loads(f) if isinstance(f,str) else f
                except ValueError:continue
                cid=tc.get("id")
                if fn.get("name")=="bash" and isinstance(arg,dict) and isinstance(arg.get("command"),str) and cid:byid[cid]=(i,arg['command'])
        elif m.get("role")=="tool" and m.get("tool_call_id") in byid:
            j,cmd=byid.pop(m["tool_call_id"]);yield i,cmd,m
def main():
    published=get(V/"memory-stage-fetch/source-manifest.json");available={v["rfilename"]:v for v in published['siblings']}
    roster=[];events=[];unsupported=[];ct=collections.defaultdict(collections.Counter);shape=collections.Counter()
    for repo in REPOSITORIES:
        for path in sorted((H/repo.replace("/","__")).glob("*/*.traj.json")):
            blob=path.read_bytes();key=path.relative_to(V/"benchmark").as_posix();meta=available[key]
            expected=meta.get("lfs",{}).get("sha256") or meta["blobId"];actual=h(blob) if len(expected)==64 else hashlib.sha1(b"blob "+str(len(blob)).encode()+b"\0"+blob).hexdigest()
            assert actual==expected,(path,expected,actual)
            msgs=json.loads(blob)["messages"];user=next((v["content"] for v in msgs if v["role"]=="user"),"");issue=user.partition("</pr_description>")[0]
            iid=path.parent.name;counts=ct[repo];counts["files"]+=1
            if BAD.search(issue):counts["topic_excluded"]+=1;continue
            roster.append(dict(repo=repo,iid=iid,file=key,sha=h(blob),upstream=expected));roots=source(repo);cs=list(pairs(msgs));counts["calls"]+=len(cs)
            attest="/testbed (this is the working directory" in user or "working directory is /testbed" in user
            for i,cmd,row in cs:
                if not SEARCH.search(cmd):continue
                counts["commands_with_search"]+=1
                raw=row.get("extra",{});code=raw.get("returncode");seen=EXIT.fullmatch(row.get('content',''));output=raw.get("raw_output")
                if not seen or type(code)!=int or int(seen[1])!=code:counts["unmatched_numeric_codes"]+=1;continue
                counts["numeric_code_"+str(code)]+=1
                if code!=1:continue
                if not isinstance(output,str) or output.strip() or seen[2].strip() or raw.get("exception_info"):
                    counts["code1_nonempty_or_exception"]+=1;continue
                if not attest and not cmd.lstrip().startswith("cd /"):
                    counts["cwd_unattested"]+=1;continue
                sk,why=parse(cmd,"/testbed",roots)
                if why:
                    counts["excluded_"+why]+=1
                    unsupported.append([iid,i,why,h(cmd.encode())])
                    continue
                counts["strict_events"]+=1
                again=any(parse(c,"/testbed",roots)[0]==sk for j,c,_ in cs if j>i and SEARCH.search(c))
                events.append(dict(iid=iid,repo=repo,step=i,key=sk,command=cmd,raw=output,shown=row["content"],code=code,observable_later_repeat=again,tool_call_id=row["tool_call_id"]))
    keys={};groups=collections.defaultdict(set)
    for note in events:
        x=note['key'];semantic=tuple((u,str(v)) for u,v in x.items() if u not in ('tool','root'))
        label=(note['iid'],semantic)
        if label not in keys:keys[label]=note
        groups[note['repo']].add(note['iid'])
    groups={repo:sorted(ids,key=lambda i:h(("R12-explicit-absence|"+i).encode())) for repo,ids in groups.items()}
    select=[group[i] for i in range(max((len(x) for x in groups.values()),default=0)) for _,group in sorted(groups.items()) if i<len(group)][:96]
    selected=[v for v in keys.values() if v['iid'] in select]
    save("roster.json",roster);save("coverage.json",ct);gz("raw_empty_events.json.gz",events);gz("unsupported.json.gz",unsupported);save("keys.json",selected)
    save("input.lock.json",{"source":published['id'],"revision":published['sha'],"roster":len(roster),"unique_keys_before_cap":len(keys),"eligible_tasks_before_cap":sum(map(len,groups.values())),"selected_tasks":len(select),"selected_keys":len(selected),"files":{n:h((D/n).read_bytes()) for n in ["extract.py","PROTOCOL_RU.md","roster.json","coverage.json","raw_empty_events.json.gz","unsupported.json.gz","keys.json"]}})
    print(get(D/"input.lock.json"));print({repo:(z["files"],z["strict_events"]) for repo,z in ct.items()})
if __name__=="__main__":main()
