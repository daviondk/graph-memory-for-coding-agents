"""Select publicly archived one-line pytest commands without using pytest output for eligibility or the audit draw."""
from pathlib import Path
from collections import Counter,defaultdict
import re,json,gzip,hashlib,shlex,sys
D=Path(__file__).resolve().parent;W=D.parents[1]
sys.path.insert(0,str(W/"graph_memory_round12/negative_external"))
import extract as upstream
A=[r for r in upstream.REPOSITORIES if r!="mpmath/mpmath"]
B="Delgan/loguru HypothesisWorks/hypothesis ipython/traitlets pallets/click pypa/setuptools python-attrs/attrs scikit-build/scikit-build-core theacodes/nox".split()
BAD=re.compile(r"\b(?:CVE-\d{4}|security flaw|security vulnerability|vulnerabilit(?:y|ies)|exploit(?:ation)?|XSS|SQL injection|path traversal|remote code execution)\b",re.I)
WRAP=re.compile(r"\A\s*<returncode>\s*(-?\d+)\s*</returncode>\s*<output>(.*?)</output>\s*\Z",re.S)
def sha(b):return hashlib.sha256(b).hexdigest()
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def put(p,x):
    b=json.dumps(x,ensure_ascii=False,indent=None if p.suffix==".gz" else 2,sort_keys=True).encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def parse(cmd):
    if "\n" in cmd or "\r" in cmd or "\x60" in cmd or "$(" in cmd:return None
    try:
        parser=shlex.shlex(cmd,punctuation_chars=";&|",posix=True)
        parser.whitespace_split=True;t=list(parser)
    except ValueError:return None
    groups=[];links=[];curr=[]
    for word in t:
        if word in ("||","&&",";","|","&"):
            if curr:groups.append(curr);curr=[];links.append(word)
        else:curr.append(word)
    if curr:groups.append(curr)
    def pytest_command(x):
        i=0
        while i<len(x) and re.fullmatch(r"(?:[A-Za-z_]\w*=.*|env)",x[i]):i+=1
        if i==len(x):return False
        exe=x[i].rsplit("/",1)[-1]
        return exe in ("pytest","py.test") or (bool(re.fullmatch(r"python(?:\d+(?:\.\d+)?)?",exe)) and x[i+1:i+3]==["-m","pytest"])
    cand=[j for j,group in enumerate(groups) if pytest_command(group)]
    if len(cand)!=1:return None
    idx=cand[0]
    # shlex tokenizes 2>&1 at &, which is a redirection and not shell control flow.
    clean=re.sub(r"\d*>&\d+","",cmd)
    if clean!=cmd:return parse(clean)
    pre=groups[:idx]
    if any(x[0] not in {"cd","set","source",".","export","pwd"} for x in pre):return None
    if any(link not in (";","&&") for link in links[:idx]):return None
    post=links[idx:]
    piped="|" in post
    direct=not post and all(l=="&&" or (g and g[0] in ("set","export")) for l,g in zip(links[:idx],pre))
    safe_pipe=any(g==["set","-o","pipefail"] or g==["set","-e","-o","pipefail"] for g in pre) and all(l=="|" for l in post)
    return dict(piped=piped,direct=direct,pipefail=safe_pipe,shape="direct" if direct else "pipefail" if safe_pipe else "pipeline" if piped else "compound",
                args=groups[idx])
def main():
    items=[];files={};allcounts={};seen=set()
    manifest=get(upstream.V/"memory-stage-fetch/source-manifest.json")
    revision=manifest["sha"];assert revision=="11164976b4f920cdb0d0cd570ca572e49acea1e8"
    for panel,repos in (("science",A),("other",B)):
        ct=Counter()
        for repo in repos:
            for f in sorted((upstream.H/repo.replace("/","__")).glob("*/*.traj.json")):
                source=f.read_bytes();data=json.loads(source);msgs=data["messages"];ct["file"]+=1
                user=next((m.get("content","") for m in msgs if m.get("role")=="user"),"")
                if BAD.search(user.partition("</pr_description>")[0]):ct["out_of_scope"]+=1;continue
                iid=f.parent.name
                assert (repo,iid) not in seen;seen.add((repo,iid))
                files[f.relative_to(upstream.V).as_posix()]=sha(source)
                for pos,cmd,msg in upstream.pairs(msgs):
                    if not re.search(r"\b(?:pytest|py\.test)\b",cmd):continue
                    ct["mention"]+=1;kind=parse(cmd)
                    if not kind:continue
                    ct["command"]+=1;ex=msg.get("extra",{});rc=ex.get("returncode");raw=ex.get("raw_output");wrap=WRAP.fullmatch(msg.get("content",""))
                    if type(rc)!=int or not wrap or int(wrap[1])!=rc or not isinstance(raw,str):ct["no_code_pair"]+=1;continue
                    key=sha((repo+"|"+iid+"|"+msg["tool_call_id"]).encode())[:24]
                    items.append(dict(id=key,repo=repo,iid=iid,panel=panel,step=pos,tool_call_id=msg["tool_call_id"],cmd=cmd,
                        kind=kind,rc=rc,visible=wrap[2].strip("\r\n"),raw=raw,exception=ex.get("exception_info","")))
                    ct["eligible"]+=1
        allcounts[panel]=ct
    ids=sorted(items,key=lambda x:sha(("receipt:audit:"+x["id"]).encode()))
    first=ids[:24];selected={x["id"] for x in first}
    pipe=[x for x in ids if x["id"] not in selected and x["kind"]["piped"]][:24]
    cards=[];key={}
    for label,group in (("uniform",first),("pipe",pipe)):
        for index,x in enumerate(group):
            blind="C"+sha(("blind:"+x["id"]).encode())[:9];key[blind]=dict(id=x["id"],stratum=label)
            # Panellists see terminal output only. Keep original final lines (full bytes available if needed).
            lines=x["visible"].splitlines()
            cards.append(dict(card=blind,shown_lines=len(lines),tail="\n".join(lines[-16:])[-1400:]))
    put(D/"cohort.json",dict(counts=allcounts,revision=revision,source_files=files,panel_A=A,panel_B=B,unique_traces=len(seen)))
    put(D/"calls.gz",items);put(D/"audit-cards.json",sorted(cards,key=lambda v:v["card"]));put(D/"audit-key.json",key)
    put(D/"input-lock.json",{n:sha((D/n).read_bytes()) for n in ("PROTOCOL_RU.md","collect.py","cohort.json","calls.gz","audit-cards.json","audit-key.json")})
    print(len(items),allcounts,len(cards))
if __name__=="__main__":main()
