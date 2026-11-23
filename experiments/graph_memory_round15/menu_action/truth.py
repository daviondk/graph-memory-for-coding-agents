"""Open reference outcomes only after all model choices and real read receipts are sealed."""
import collections,concurrent.futures,json,os,subprocess,sys
from pathlib import Path
from menu import D,F,h,encode,read,put,lock
R13=D.parents[1]/"graph_memory_round13/reformulation"
R14=D.parents[1]/"graph_memory_round14/grounded"
sys.path.insert(0,str(R13))
import prefix,pr_oracle
def main():
    for name in ("assignment.json","action.lock.json","read.lock.json","blob.lock.json"):lock(D/name)
    source=read(F/"outcome.lock.json");assert source["forecast_lock"]==h((F/"forecast.lock.json").read_bytes())
    for n,s in source["files"].items():assert h((F/n).read_bytes())==s
    existing=read(F/"outcomes.json.gz");bench=read(F/"official_patch_paths.json.gz");old={r["id"]:r for rows in existing.values() for r in rows}
    cases=read(D/"menus.json.gz");prefix.D=pr_oracle.D=D;(D/"pr_refs").mkdir(exist_ok=True);pr_oracle.CACHE=D/"vendor_git"
    # Recheck parent, diff, production filter and time at this cohort's actual revisions.
    for c in cases:
        for prev in (R13/"pr_refs",R13/"replication/pr_refs",R14/"pr_refs"):
            loc=prev/(c["iid"]+".json")
            if loc.is_file():
                rec=read(loc)
                if rec.get("status")=="ok" and rec["repo"]==c["repo"]:
                    put(D/"pr_refs"/loc.name,rec);break
    pairs=[(c["iid"],c["repo"]) for c in cases]
    with concurrent.futures.ThreadPoolExecutor(5) as pool:rs=list(pool.map(pr_oracle.meta,pairs))
    by=collections.defaultdict(list)
    for c,r in zip(cases,rs):
        assert c["iid"]==r["iid"] and bench[c["iid"]]["base"]==c["base"]
        r["base"]=c["base"]
        if r["status"]=="ok":by[r["repo"]].append(r)
    def fetch(group):
        try:pr_oracle.fetch(group)
        except (OSError,RuntimeError,subprocess.SubprocessError) as exc:
            for rec in group[1]:
                try:pr_oracle.fetch((group[0],[rec]))
                except (OSError,RuntimeError,subprocess.SubprocessError) as e:rec.update(status="git_unavailable",error=str(e)[:240])
    with concurrent.futures.ThreadPoolExecutor(5) as pool:list(pool.map(fetch,by.items()))
    labels={}
    rosters=read(F/"rosters.json.gz");input_rows=read(F/"frontier_inputs.json.gz")
    for c,r in zip(cases,rs):
        oldrow=old[c["id"]];fkey=next(row["key"] for row in input_rows[c["panel"]] if row["id"]==c["id"])
        task=next(u for u in rosters[c["panel"]] if u["iid"]==c["iid"])
        raw=(prefix.V/"benchmark"/task["file"]).read_bytes();assert h(raw)==task["sha"]
        steps=list(prefix.calls(json.loads(raw)["messages"]));idx=c["step"]
        assert steps[idx][2]==c["id"].split("|",1)[1]
        observed=[]
        for j,mi,cid,command,tool in steps[idx+1:idx+6]:
            rc,visible=prefix.shown(tool)
            if rc!=0 or not visible:continue
            files=prefix.inspect(command,visible,c["repo"])
            if len(files)==1 and files[0][0]==fkey["root"] and files[0][2]!="grep-list":
                observed.append({"path":files[0][1],"kind":files[0][2],"delta":j-idx,"call":cid,"visible_sha":h(visible.encode())})
        nextpath=[observed[0]["path"]] if observed else []
        assert nextpath==oldrow["next"]
        if oldrow["strict_available"]:
            assert r.get("strict") and r["prod"]==oldrow["patch_strict"]
        status=r["status"] if r["status"]!="ok" else "not_direct" if not r["strict"] else "no_old_production_change" if not r["prod"] else "strict_production_change"
        labels[c["id"]]={"iid":c["iid"],"panel":c["panel"],"repo":c["repo"],"base":c["base"],"pr":r,"status":status,"next":nextpath,
                         "following_observations":observed,"frontier_had_strict":oldrow["strict_available"],"official_patch":oldrow["patch_official"]}
    misses=[]
    for rec in read(D/"reads.json.gz"):
        if rec["opened"] or not rec["path"]:continue
        mirror=pr_oracle.CACHE/(rec["repo"].replace("/","__")+".git")
        def git(*args):
            return subprocess.run(["git","-C",str(mirror),*args],capture_output=True,timeout=90,env={**os.environ,"GIT_TERMINAL_PROMPT":"0"})
        if git("cat-file","-e",rec["base"]+"^{tree}").returncode:
            q=git("fetch","--no-tags","--depth=1","--filter=blob:none","origin",rec["base"])
            if q.returncode:misses.append({"id":rec["id"],"arm":rec["arm"],"verified":False});continue
        cmd=git("ls-tree","-z",rec["base"],"--",rec["path"]);assert cmd.returncode==0
        misses.append({"id":rec["id"],"arm":rec["arm"],"path":rec["path"],"verified_absent":not bool(cmd.stdout),"stdout":cmd.stdout.decode()})
    put(D/"heldout.json.gz",labels);put(D/"absent_reads.json",misses)
    put(D/"truth.lock.json",{n:h((D/n).read_bytes()) for n in ("read.lock.json","heldout.json.gz","absent_reads.json","truth.py")})
    print(collections.Counter(v["status"] for v in labels.values()),"old strict available:",sum(v["frontier_had_strict"] for v in labels.values()))
if __name__=="__main__":main()
