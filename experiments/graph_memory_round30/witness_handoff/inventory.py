"""Inventory proven duplicate observations. No trajectory action, code or command is ever executed."""
from pathlib import Path,PurePosixPath
from collections import Counter,defaultdict
from hashlib import sha256
import sys,json,re,gzip
import pyarrow.parquet as pq
D=Path(__file__).resolve().parent;P=Path("D:/CodexResearch/x20-r30-witness")
SWE=Path("D:/CodexResearch/x20-r27-code-data")
SPL=Path("D:/CodexResearch/x20-isetrace-runtime/inputs/trajectories")
R27=D.parents[1]/"graph_memory_round27"/"code_boundary"
sys.path.insert(0,str(R27))
from prepare import ALLOW,prod,RISK
def h(x): return sha256(x.encode()).hexdigest()
def save(p,x):
    b=(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
    return sha256(p.read_bytes()).hexdigest()
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
allow=re.compile(r"\b(?:meetings?|conference|workshops?|classroom|teachers?|students?|education|academic|articles?|manuscripts?|editors?|museums?|librar\w+|gardens?|recipes?|catering|restaurants?|bookstores?|music|performances?|retail|marketing|sales|revenue|customers?|tourism|hotels?|hospitality|travel|transportation|design|invoices?|bookkeeping|inventory|logistics|architecture|accounting|events?|publish\w+|suppliers?)\b",re.I)
extra=re.compile(r"\b(?:bio(?:logy|logical|tech\w*)|virus(?:es)?|bioweapon\w*|genom\w*|DNA|RNA|traffick\w*|military|munitions?|defen[cs]e|terror\w*|armed|combat|gunfire|bomb\w*|troops?|police|fraud|medical|clinical|hospital|patient|diagnos\w*|forensic|intelligence agency|geopoliti\w*)\b",re.I)
def swe():
    meta={r["instance_id"]:r for r in pq.read_table(SWE/"verified.parquet",columns=["repo","instance_id","base_commit","problem_statement"]).to_pylist()}
    n=Counter();rows=[]
    for line in (SWE/"swe-explore.jsonl").open(encoding="utf8"):
        row=json.loads(line);m=meta.get(row["instance_id"])
        if row["dataset"]!="verified" or not m or m["repo"] not in ALLOW or RISK.search(m["problem_statement"]):continue
        n["benign_issues"]+=1;ev=[]
        for path,records in row["read_step_info"].items():
            if not prod(path):continue
            for a in records:
                n["raw_records"]+=1;s,e=a["start"],a["end"]
                if not 0<s<=e:continue
                ev.append((h(path),h(a["traj_path"]),a["step_idx"],s,e))
        ev=sorted(set(ev));n["bounded_distinct_accesses"]+=len(ev);n["issues_bounded"]+=bool(ev)
        same=other=False
        for i,(path,t,j,l,u) in enumerate(ev):
            for path2,t2,j2,l2,u2 in ev[:i]:
                if path!=path2 or max(l,l2)> min(u,u2):continue
                if t==t2:same|=(j!=j2)
                else:other=True
        n["issues_repeated_same_run"]+=same;n["issues_repeated_across_runs"]+=other
        if ev:rows.append(dict(issue=h(row["instance_id"]),repo=m["repo"],commit=m["base_commit"],events=ev))
    rec=save(P/"swe-events.json.gz",rows)
    return dict(counts=n,projection_sha=rec)
def lines(text,offset):
    for i,s in enumerate(text.splitlines(),offset):
        raw=s.encode()
        if not 32<=len(raw)<=320 or len(set(re.findall(r"[a-z]{2,}",s.lower())))<4:continue
        if re.search(r"truncat|output clipped|more lines|continue reading|use offset|output omitted|failed to read|error reading",s,re.I):continue
        yield i,s
def isetrace(aliases=("path","file_path"),panel="ise"):
    stats=Counter();rows=[];sources=[]
    for f in sorted(SPL.glob("trajectories-*.jsonl")):
        sha=sha256()
        with f.open("rb") as inp:
            for line in inp:
                sha.update(line);r=json.loads(line);stats["trajectories"]+=1
                prompt=" ".join(str(s["natural_language_intent"]) for s in r["source_intents"])
                if not allow.search(prompt) or RISK.search(prompt) or extra.search(prompt):continue
                stats["eligible_benign"]+=1;q=r["session_id"];messages=r["messages"];args={};ev=[];seen=defaultdict(set);send=[];calls=Counter();known=defaultdict(set);nr=0
                for j,m in enumerate(messages):
                    if m["role"]=="assistant":
                        for a in m.get("tool_calls",[]):
                            fn=a.get("function",{});name=fn.get("name")
                            if name not in ("read","sessions_send","sessions_spawn","subagents"):continue
                            try:
                                params=fn.get("arguments",{});params=json.loads(params) if isinstance(params,str) else params
                                if not isinstance(params,dict):continue
                                args[a["id"]]=(name,params)
                            except (TypeError,ValueError,KeyError):continue
                        continue
                    if m["role"]!="tool" or m.get("tool_call_id") not in args:continue
                    name,params=args[m["tool_call_id"]];calls[name+"_attempts"]+=1
                    if not m.get("success"):continue
                    calls[name+"_success_field"]+=1
                    if name=="sessions_send":
                        payload=params.get("message")
                        if not isinstance(payload,str):continue
                        sent={s for s in known if s in payload};calls["sends_with_exact_prior_line"]+=bool(sent);send.append([j,len(sent)]);continue
                    if name!="read":continue
                    path=next((params[z] for z in aliases if isinstance(params.get(z),str)),None);txt=m.get("content")
                    if not isinstance(path,str) or not isinstance(txt,str):continue
                    if not (path.startswith("/workspace/") and PurePosixPath(path).suffix.lower() in {".md",".txt",".csv",".tsv",".rst"} and ".." not in PurePosixPath(path).parts) or RISK.search(path) or extra.search(path) or RISK.search(txt) or extra.search(txt):continue
                    if len(txt)>64000 or not txt.strip() or txt.lstrip().startswith(("{","[")) and '"error"' in txt[:256]:continue
                    try:offset=int(params.get("offset",1))
                    except (ValueError,TypeError):continue
                    if offset<1:continue
                    p=h(path);parts=[]
                    for ln,s in lines(txt,offset):
                        code=h(s);parts.append([ln,code,len(s.encode())]);seen[(p,ln,code)].add(j);known[s].add(j)
                    if parts:ev.append(dict(id=j,path=p,lines=parts));nr+=len(parts)
                stats.update(calls);stats["sessions_with_send_attempt"]+=bool(calls["sessions_send_attempts"]);stats["sessions_with_send_success_flag"]+=bool(calls["sessions_send_success_field"]);stats["sessions_with_matching_send"]+=any(n for _,n in send)
                stats["eligible_read_events"]+=len(ev);stats["eligible_line_receipts"]+=nr;stats["sessions_with_read"]+=bool(ev)
                stats["sessions_with_two_reads"]+=len(ev)>=2
                stats["sessions_with_repeated_coordinate_and_payload"]+=any(len(ids)>1 for ids in seen.values());stats["unique_coordinate_payloads"]+=len(seen);stats["coordinate_payloads_with_multiple_receipts"]+=sum(len(ids)>1 for ids in seen.values())
                if ev:rows.append(dict(id=q,events=ev,sends=send))
        sources.append(dict(name=f.name,bytes=f.stat().st_size,sha256=sha.hexdigest()))
    rec=save(P/(panel+"-events.json.gz"),rows);assert len(rows)==len({r["id"] for r in rows})
    return dict(counts=stats,projection_sha=rec,shards=sources)
if __name__=="__main__":
    P.mkdir(exist_ok=True);which=sys.argv[1];out={"swe":swe,"ise":isetrace,"ise4":lambda:isetrace(("path","file_path","filePath","file"),"ise4")}[which]();save(D/(which+"-inventory.json"),out);print(which,out["counts"])

