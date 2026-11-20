"""Expose only public issue text, agent file ranks and base SHAs. Gold is deliberately unopened."""
from pathlib import Path
import collections, concurrent.futures, gzip, hashlib, json, os, re, subprocess
import pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parent
DENY=re.compile(r"\b(?:vulnerabilit(?:y|ies)|CVE[- ]?\d+|exploit(?:ation)?|SQL injection|code injection|remote code execution|cross.site scripting|denial.of.service|bypass(?:ing)? (?:authentication|authorization|security)|malware|path traversal|credential theft)\b",re.I)
ENV={**os.environ,"GIT_TERMINAL_PROMPT":"0","GCM_INTERACTIVE":"Never","GIT_NO_LAZY_FETCH":"1","GIT_ALLOW_PROTOCOL":"file"}
def write(path,obj):
    path.write_bytes(gzip.compress(json.dumps(obj,separators=(",",":"),ensure_ascii=True).encode(),mtime=0))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(repo,*args,env=ENV):
    return subprocess.run(["git","-c","credential.helper=","-C",str(repo),*args],env=env,check=True,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120).stdout
def extract(pair):
    rep,base=pair;dest=ROOT/"history"/(base+".json.gz")
    if dest.exists():return
    repo=ROOT/"mirrors"/rep.replace("/","__")
    try:
        entries=git(repo,"ls-tree","-r","--name-only","-z",base).decode("utf8",errors="surrogateescape").split("\0")
        # Keep whole event boundaries; no filtering commit history by Python paths before sampling windows.
        payload=git(repo,"-c","core.quotepath=false","log","--max-count=384","--first-parent",
                    "--diff-merges=first-parent","--no-renames","--format=%x1e%H%x1f%s","--name-only",base)
        commits=[]
        for rec in payload.decode("utf8","replace").split("\x1e")[1:]:
            header,*others=rec.splitlines()
            oid,subject=header.split("\x1f",1)
            assert re.fullmatch(r"[a-f0-9]{40}",oid)
            names=sorted({line for line in others if line.endswith(".py")})
            commits.append([oid,subject,names])
        assert commits[0][0]==base
        write(dest,{"base":base,"files":sorted(x for x in entries if x.endswith(".py")),"events":commits})
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
        write(dest,{"base":base,"unavailable":type(exc).__name__})
def main():
    src=ROOT/"input/loc_outputs.jsonl";ds=ROOT/"input/locagent_test.parquet"
    official={r["instance_id"]:r["created_at"] for r in pq.read_table(ds,columns=["instance_id","created_at"]).to_pylist()}
    items=[]
    for line in src.read_text(encoding="utf8").splitlines():
        row=json.loads(line);i=row["instance_id"]
        if i not in official:continue
        m=row["meta_data"]
        assert isinstance(m["base_commit"],str)
        text=m["problem_statement"]
        items.append({"id":i,"repo":m["repo"],"date":str(official[i]),"base":m["base_commit"],
                      "question":"" if DENY.search(text) else text,"excluded":bool(DENY.search(text)),
                      "native":row["found_files"]})
    assert len(items)==len(official)==274
    write(ROOT/"input/questions.json.gz",items)
    (ROOT/"history").mkdir(exist_ok=True)
    pairs=sorted({(r["repo"],r["base"]) for r in items if not r["excluded"]})
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for _ in ex.map(extract,pairs):pass
    docs=sorted((ROOT/"history").glob("*.gz"))
    status={"n":len(items),"excluded":sum(r["excluded"] for r in items),"revisions":len(pairs),
            "git":subprocess.check_output(["git","--version"]).decode().strip(),
            "sources":{p.name:sha(p) for p in (src,ds,ROOT/"input/eval_metric.py",ROOT/"input/questions.json.gz",ROOT/"PROTOCOL.md")},
            "history":{p.name:sha(p) for p in docs}}
    (ROOT/"sources.json").write_text(json.dumps(status,indent=2),encoding="utf8")
    print({k:status[k] for k in ("n","excluded","revisions","git")},flush=True)
if __name__=="__main__":main()

