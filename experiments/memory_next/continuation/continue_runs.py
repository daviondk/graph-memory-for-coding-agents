"""Local blind continuation runner. Run only after the preceding GPU experiment is sealed."""
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import requests
from handoff import OLD, ROOT, SYSTEM, TOOL, create as make_handoff, items, read, sha, write_json

sys.path.insert(0, str(OLD))
from workspace import create, docker, patch, shell

URL="http://127.0.0.1:18839/replicate/0/v1/chat/completions"
MODEL="qwen38-27b-ud-q4km"

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def clipped(s):
    return s if len(s)<=6000 else s[:4000]+"\n[part omitted]\n"+s[-2000:]

def journal(p,data):
    with p.open("a",encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False)+"\n")
        f.flush()
        os.fsync(f.fileno())

def apply_snapshot(cid, file):
    expected=file.read_bytes()
    if expected:
        path="/mnt/d/"+file.resolve().as_posix()[3:]
        docker(["cp",path,cid+":/tmp/handed.patch"])
        done=shell(cid,"git apply --binary --whitespace=nowarn /tmp/handed.patch")
        if done.returncode:raise RuntimeError(done.stderr.decode("utf-8","replace"))
        docker(["exec","--user","0",cid,"rm","-f","/tmp/handed.patch"])
    actual=patch(cid)
    if actual!=expected:
        raise RuntimeError(f"snapshot mismatch {sha(actual)} != {sha(expected)}")
    return sha(actual)

def run(row,arm,proof):
    iid=row["id"]
    out=ROOT/"runs"/iid/arm
    out.mkdir(exist_ok=True,parents=True)
    if (out/"complete.json").exists():
        c=read(out/"complete.json")
        assert sha((out/"candidate.patch").read_bytes())==c["patch_sha256"]
        return
    dest=ROOT/"handoffs"/iid
    if not (dest/"input_lock.json").exists():make_handoff(iid)
    lock=read(dest/"input_lock.json")
    assert lock["model"]==MODEL
    for name,h in lock["files"].items():assert sha((dest/name).read_bytes())==h
    input_hash=sha((dest/"input_lock.json").read_bytes())
    content=(dest/"common_user.txt").read_bytes().decode("utf-8")
    if arm=="manifest":content+=(dest/"manifest_only.txt").read_bytes().decode("utf-8")
    initial=[{"role":"system","content":SYSTEM},{"role":"user","content":content}]
    cid=create(row,proof)
    start=time.monotonic()
    attempts=out/"runner_events.jsonl"
    try:
        initial_hash=apply_snapshot(cid,dest/"inherited.patch")
        msgs=initial[:]
        checkpoint=out/"checkpoint.json"
        totals=[0,0]; used=0; reason="call_limit";finished=False
        if checkpoint.exists():
            saved=read(checkpoint)
            assert saved["input_hash"]==input_hash
            # Rebuild a fresh clean checkout to apply the complete cumulative diff.
            docker(["rm","-f",cid])
            cid=create(row,proof)
            resumed_hash=apply_snapshot(cid,out/saved["snapshot"])
            assert resumed_hash==saved["snapshot_sha256"]
            msgs=saved["messages"]; totals=saved["totals"]; used=saved["completed"];reason=saved["reason"];finished=saved["terminal"]
            assert msgs[:2]==initial
        journal(attempts,{"time":now(),"type":"start","restored_turns":used,"initial_tree_sha256":initial_hash,"input_hash":input_hash,"model":MODEL,"source_image":proof["image_id"]})
        for t in range(used, 8):
            if finished:break
            seed=int(sha(("continuation-v1|"+iid+"|"+str(t)).encode())[:8],16)%(2**31-1)
            p={"model":MODEL,"messages":msgs,"tools":[TOOL],"temperature":.5,"top_p":.95,"seed":seed,"max_tokens":768,"stream":False}
            pp=out/f"prompt-{t+1:02}.json"; rr=out/f"response-{t+1:02}.json"
            if pp.exists():assert read(pp)==p
            else:write_json(pp,p)
            if rr.exists():
                response=read(rr)
                journal(attempts,{"time":now(),"turn":t+1,"type":"cache_response"})
            else:
                try:
                    raw=requests.post(URL,json=p,timeout=650)
                    raw.raise_for_status()
                    response=raw.json()
                    write_json(rr,response)
                except Exception as e:
                    journal(attempts,{"time":now(),"turn":t+1,"type":"http_error","error":str(e)})
                    raise
            answer=response["choices"][0]["message"]
            totals[0]+=response["usage"]["prompt_tokens"];totals[1]+=response["usage"]["completion_tokens"]
            msg={"role":"assistant","content":answer.get("content") or ""}
            calls=answer.get("tool_calls") or []
            if calls:msg["tool_calls"]=calls
            msgs.append(msg)
            acts=[]
            for k,c in enumerate(calls):
                fn=c.get("function",{});name=fn.get("name");orig=fn.get("arguments","{}")
                tick=time.perf_counter();stdout=stderr="";err=None
                try:
                    args=json.loads(orig) if isinstance(orig,str) else orig
                    if name=="bash":
                        cp=shell(cid,args["command"]);stdout=cp.stdout.decode("utf-8","replace");stderr=cp.stderr.decode("utf-8","replace")
                        shown="Exit "+str(cp.returncode)+"\n"+clipped(stdout+("\n"+stderr if stderr else ""))
                    else:shown="Unknown tool."
                except (ValueError,KeyError,TypeError) as e:shown="Invalid tool arguments";err=str(e)
                acts.append({"turn":t+1,"index":k,"name":name,"arguments":orig,"seconds":time.perf_counter()-tick,
                             "stdout":stdout,"stderr":stderr,"context_output":shown,"error":err})
                msgs.append({"role":"tool","tool_call_id":c["id"],"content":shown})
            # A complete state checkpoint decouples an accepted response from retries.
            write_json(out/f"actions-{t+1:02}.json",acts)
            snapshot=f"state-{t+1:02}.patch"; state=patch(cid)
            (out/snapshot).write_bytes(state)
            finished=not bool(calls)
            if finished:reason="final_message"
            used=t+1
            write_json(checkpoint,dict(completed=used,totals=totals,messages=msgs,snapshot=snapshot,snapshot_sha256=sha(state),
                                       input_hash=input_hash,reason=reason,terminal=finished))
            journal(attempts,{"time":now(),"type":"turn_committed","turn":used,"input_tokens":response["usage"]["prompt_tokens"],"output_tokens":response["usage"]["completion_tokens"]})
        diff=patch(cid)
        (out/"candidate.patch").write_bytes(diff)
        all_actions=[a for t in range(1,used+1) for a in read(out/f"actions-{t:02}.json")]
        (out/"actions.jsonl").write_bytes("".join(json.dumps(a,ensure_ascii=False)+"\n" for a in all_actions).encode("utf-8"))
        journal(attempts,{"time":now(),"type":"complete","seconds_this_session":time.monotonic()-start})
        first=items(attempts)[0]["time"]
        write_json(out/"complete.json",{"id":iid,"arm":arm,"model":MODEL,"calls":used,"input_tokens":totals[0],"output_tokens":totals[1],
                   "elapsed_s":(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(first)).total_seconds(),"finish_reason":reason,
                   "finished":now(),"patch_bytes":len(diff),"patch_sha256":sha(diff),"input_lock_sha256":input_hash,
                   "initial_tree_sha256":initial_hash,"final_changed_vs_initial":sha(diff)!=initial_hash,"source_image":proof["image_id"]})
        print(iid,arm,"sealed",used,len(diff),flush=True)
    finally:
        docker(["rm","-f",cid],check=False)

def main():
    guard=ROOT.parent/"time_read"/"end_lock.json"
    if not guard.exists():
        raise RuntimeError("time_read has not released the GPU")
    for name,h in read(ROOT/"design_lock.json")["sha256"].items():assert sha((ROOT/name).read_bytes())==h
    for name,h in read(ROOT/"implementation_lock.json")["sha256"].items():assert sha((ROOT/name).read_bytes())==h
    ids=read(ROOT/"assignments.json")
    tasks={r["id"]:r for r in read(OLD/"public_tasks.json")}
    proofs=read(OLD/"images.json")
    for iid in sorted(set(i for i,a in ids)):
        if not (OLD/"runs"/iid/"brief"/"complete.json").exists():raise RuntimeError("missing predecessor "+iid)
        if not (ROOT/"handoffs"/iid/"input_lock.json").exists():make_handoff(iid)
    for iid,arm in ids:run(tasks[iid],arm,proofs[iid])
    files={f.relative_to(ROOT).as_posix():sha(f.read_bytes()) for d in ["runs","handoffs"] for f in sorted((ROOT/d).rglob("*")) if f.is_file()}
    for name in ["design_lock.json","implementation_lock.json","assignments.json","PROTOCOL.md"]:files[name]=sha((ROOT/name).read_bytes())
    write_json(ROOT/"end_lock.json",{"time":now(),"files":files,"time_read_lock_sha256":sha(guard.read_bytes())})

if __name__=="__main__":main()

