"""Measure recovery paths after address failures and compare chronological transfer with Python conventions."""
import collections,concurrent.futures,gzip,json,re,urllib.request
from pathlib import PurePosixPath
from classify import cleanpath
from git_pairs import D,get,get_http,git,local,save,sha
def recover(pair):
    row,original,pr=pair
    with urllib.request.urlopen(original["url"],timeout=30) as f:raw=f.read()
    assert sha(raw)==original["sha"]
    obs=json.loads(gzip.decompress((D/"observations"/(row["iid"]+".json.gz")).read_bytes()))["steps"]
    steps=json.loads(raw)["trajectory"]
    old=row["base"];repo=row["repo"];p=row["key"]["literal"]
    dates=get_http(pr["api"]);assert dates["merge_commit_sha"]==pr["new"]
    target=None;events=[]
    names=set(s.decode() for s in git(local(repo),"ls-tree","-r","-z","--name-only",old).stdout.split(b"\0") if s)
    for ix in range(row["step"]+1,min(row["step"]+7,len(steps))):
        v=obs[ix]
        if not v or v["args"].get("command")!="view":continue
        actual=steps[ix].get("observation","");assert sha(actual.encode())==v["raw_sha"]
        path=cleanpath(v["args"].get("path",""),v["cwd"])
        # Public SWE-agent editor prefixes contain the full path and numbered file content.
        first=actual.splitlines()[0] if actual else ""
        header_ok=("cat -n" in first and v["args"]["path"] in first) or first.startswith("<NOTE>This file is too large to display entirely. Showing abbreviated version.")
        numbered=re.findall(r"(?m)^[ \t]*([1-9]\d*)[ \t](.*)$",actual)
        body_ok=False
        if header_ok and path in names:
            source=git(local(repo),"show",old+":"+path).stdout.decode("utf8",errors="replace").splitlines()
            checks=[1<=int(n)<=len(source) and line.rstrip()==source[int(n)-1].rstrip() for n,line in numbered[:6]]
            body_ok=len(checks)>=3 and all(checks)
        ok=bool(header_ok and body_ok and path in names)
        events.append({"step":ix,"path":path,"header":first[:400],"numbered":body_ok,"original_sha":v["raw_sha"],"verified":ok})
        if ok:target=path;break
    module=p[:-3]+"/__init__.py" if p.endswith(".py") else None
    suffix=sorted(x for x in names if x==p or x.endswith("/"+p))
    return {"iid":row["iid"],"repo":repo,"pr_number":int(dates["number"]),"merged_at":dates["merged_at"],"base":old,"wrong":p,"target":target,"after":events,"convention":module if module in names else None,"suffix":suffix[0] if len(suffix)==1 else None,"source":original["url"],"pr":pr["pr_url"]}
def main():
    tasks={r["iid"]:r for r in get(D/"roster.json")};prs={r["iid"]:r for r in get(D/"git_pairs.json")}
    orig=[(r,tasks[r["iid"]],prs[r["iid"]]) for r in get(D/"keys.json") if r["tier"]=="strict" and r["key"]["kind"]=="path"]
    with concurrent.futures.ThreadPoolExecutor(3) as ex:rows=list(ex.map(recover,orig))
    for r in rows:
        past=sorted((v for v in rows if v["repo"]==r["repo"] and v["wrong"]==r["wrong"] and v["pr_number"]<r["pr_number"] and v["merged_at"]<r["merged_at"] and v["target"]),key=lambda x:(x["merged_at"],x["pr_number"]))
        r["stored_candidate"]=past[-1]["target"] if past else None;r["source_iid"]=past[-1]["iid"] if past else None
        r["convention_then_suffix"]=r["convention"] or r["suffix"]
    save(D/"recovery.json",rows)
    print([(r["iid"],r["target"],r["after"][0]["header"][:73] if r["after"] else "") for r in rows])
if __name__=="__main__":main()
