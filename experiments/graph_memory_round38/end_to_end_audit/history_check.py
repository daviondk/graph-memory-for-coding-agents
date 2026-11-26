"""Screen historical IDs and release only source addresses that are verified in preceding commits."""
from inputs import D,R,V,KEY,COMMIT,sha,save
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from pathlib import Path
import json,re,subprocess
GITDIR=R/"ancestry.git"
SOURCE=V/"benchmark/history/python/ipython__traitlets"
STOP=(re.compile(r"(?i)(?:github\.com/ipython/traitlets/(?:issues|pull)/|(?:issues?|pull(?: request)?|pr)\s*#?\s*|#)(?:668|670)\b"),
      re.compile(r"(?i)ipython__traitlets-(?:668|670)\b"))
def ancestry(a,b):
    p=subprocess.run(["git","--git-dir",str(GITDIR),"merge-base","--is-ancestor",a,b],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);return p.returncode==0
def fetchmeta(i):
    cp=subprocess.run(["curl.exe","-fsSL","--max-time","30",f"https://api.github.com/repos/ipython/traitlets/pulls/{i}"],check=True,stdout=subprocess.PIPE)
    r=json.loads(cp.stdout)
    return {k:r[k] for k in ("number","created_at","merged_at","merge_commit_sha","title","html_url")}|{"base":r["base"]["sha"],"head":r["head"]["sha"]}
def cmdtexts(msg):
    if msg.get("role")!="assistant":return []
    out=[]
    for tc in msg.get("tool_calls",[]) or []:
        fun=tc.get("function",{}); args=fun.get("arguments")
        if isinstance(args,str):
            try:args=json.loads(args)
            except ValueError:continue
        if isinstance(args,dict) and isinstance(args.get("command"),str):out.append(args["command"])
    return out
def main():
    files=sorted(SOURCE.glob("*/*.traj.json")); assert len(files)==12
    nums=[int(p.parent.name.rsplit("-",1)[-1]) for p in files]
    with ThreadPoolExecutor(4) as ex:meta=dict(zip(nums,ex.map(fetchmeta,nums)))
    # Restrict vocabulary to tracked public Python paths in the target *base*, plus past commits.
    tree=subprocess.check_output(["git","--git-dir",str(GITDIR),"ls-tree","-r","--name-only",COMMIT],text=True).splitlines()
    paths=sorted(p for p in tree if p.startswith("traitlets/") and p.endswith(".py"))
    out=[]; aggregate=Counter()
    for i,p in zip(nums,files):
        info=meta[i]; text=p.read_text(encoding="utf8"); messages=json.loads(text)["messages"]
        old=info["merge_commit_sha"];isanc=ancestry(old,COMMIT);oldbase=ancestry(info["base"],COMMIT)
        mentioned=[a.pattern for a in STOP if a.search(text)];observe=Counter()
        historicalpaths=set(subprocess.check_output(["git","--git-dir",str(GITDIR),"ls-tree","-r","--name-only",old],text=True).splitlines()) if isanc else set()
        for m in messages:
            for cmd in cmdtexts(m):
                # Only literal pre-existing source addresses in a historical read/search command.
                # Never expose the operand after -e, a query, application text, tests, patches, tool output or reasoning.
                cmd=re.sub(r"^\s*cd\s+/(?:traitlets|testbed)/?\s*&&\s*", "", cmd).replace("/traitlets/traitlets/", " traitlets/").replace("/testbed/traitlets/", " traitlets/")
                if not re.match(r"^\s*(?:cat|rg|grep|head|tail|sed|nl)\s+",cmd):continue
                if re.search(r"[;&|<>\x60$]",cmd) or "\n" in cmd:continue
                found=set(re.findall(r"(?<![A-Za-z0-9_.\-/])(traitlets/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\.py)\b",cmd))
                for path in found & set(paths) & historicalpaths:
                    if not any(x in ("test","tests") for x in path.split("/")) and not Path(path).name.startswith("test_"):
                        observe[path]+=1
        accept=isanc and oldbase and not mentioned
        if accept:aggregate.update(observe)
        out.append(dict(id=p.parent.name,artifact_sha=sha(p),messages=len(messages),
                        roles=Counter(m["role"] for m in messages),candidate_source_mentions=dict(observe),
                        merge_is_ancestor=isanc,base_is_ancestor=oldbase,target_id_hits=len(mentioned),
                        accepted=accept,public_pr=info))
    chosen=sorted(aggregate,key=lambda p:(-aggregate[p],p))[:6]
    root=Path("D:/CodexResearch/x20-r38-traitlets-history-export")
    root.mkdir(exist_ok=True)
    # A pre-specified mechanical compression of historical *addresses*, never call it verified experience.
    content="Prior repository reads (historical frequency; verify applicability in the current checkout):\n"+ "".join(f"- {p} ({aggregate[p]} reads)\n" for p in chosen)
    target=root/"memory.txt"
    target.write_text(content,encoding="utf8")
    save(D/"history.json",dict(records=out,accepted=sum(r["accepted"] for r in out),addresses=len(chosen),
      artifact_keys_only=["messages"],compression="literal source-path counts from simple read/search call arguments only; no queries, code, instructions, tests or outputs; top6",
      allowed_sha=sha(target),export=str(root),raw_logs_for_solver=False))
    print("accepted",[(x["id"],x["merge_is_ancestor"],x["base_is_ancestor"],x["target_id_hits"]) for x in out],"safe address count",len(chosen),"manifest",sha(target))
if __name__=="__main__":main()
