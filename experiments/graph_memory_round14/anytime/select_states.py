"""Lock the state universe and selectors using only the existing public observations, before new grades."""
from pathlib import Path
from collections import defaultdict,Counter
import gzip,hashlib,json,re,shlex
D=Path(__file__).resolve().parent;WORK=D.parents[1]
CP=WORK/"graph_memory_round13/checkpoints";VIBE=WORK/"graph_memory_round12/vibe"
def sha(b):return hashlib.sha256(b).hexdigest()
def get(p):return json.loads(p.read_bytes())
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf8")
def raw_patch(digest):
    b=gzip.decompress((CP/"patches"/(digest+".patch.gz")).read_bytes());assert sha(b)==digest;return b
def simple_test(command):
    command=re.sub(r"^\s*cd\s+/testbed\s*&&\s*","",command).strip()
    if re.search(r"[|&;<>$\x60\n]",command):return False
    try:words=shlex.split(command)
    except ValueError:return False
    return bool(words and (words[0]=="pytest" or words[:3] in (["python","-m","pytest"],["python3","-m","pytest"])))
def test_evidence(msgs,events):
    actions=[];log=[]
    outputs={m.get("tool_call_id"):m.get("extra",{}) for m in msgs if m.get("role")=="tool"}
    for m in msgs:
        if m.get("role")!="assistant":continue
        ex=m.get("extra",{});acts=ex.get("actions",[])
        for action in acts:
            out=outputs.get(action.get("tool_call_id"),{});start=ex.get("timestamp");end=out.get("timestamp")
            actions.append(dict(cmd=action.get("command",""),id=action.get("tool_call_id"),start=start,end=end,output=out,count=len(acts)))
    for idx,a in enumerate(actions):
        if "pytest" not in a["cmd"]:continue
        raw=a["output"].get("raw_output","");rc=a["output"].get("returncode")
        summary=bool(re.search(r"(?m)(?:^|[= ,])([1-9]\d*) passed(?:\s|,|=|$)",raw))
        strong=simple_test(a["cmd"]) and a["count"]==1 and summary and rc==0
        note="not a standalone successful pytest";digest=None
        if strong and a["start"] and a["end"] and a["start"]<=a["end"]:
            prior=next((r for r in reversed(events) if r["at"]<=a["start"]),None)
            after=next((r for r in events if r["at"]>=a["end"]),None)
            if prior is None or after is None:note="missing time bracket"
            elif a["start"]-prior["at"]>15 or after["at"]-a["end"]>15:note="wide time bracket"
            elif prior["sha"]!=after["sha"]:note="state changed across bracket"
            elif any(j!=idx and (not x["start"] or not x["end"] or (x["start"]<after["at"] and x["end"]>prior["at"])) for j,x in enumerate(actions)):
                note="another tool action overlaps"
            else:digest=prior["sha"];note="verified bracketing samples"
        log.append(dict(action=a["id"],command=a["cmd"],output_sha=sha(raw.encode()),output_bytes=len(raw.encode()),
                        rc=rc,summary_pass=summary,single_pytest=simple_test(a["cmd"]),start=a["start"],end=a["end"],
                        bound_sha=digest,basis=note))
    bound=[(a["end"],a["bound_sha"]) for a in log if a["bound_sha"]]
    return max(bound)[1] if bound else None,log
def main():
    seal=get(CP/"sealed.json")
    for f,d in seal.items():assert sha((CP/f).read_bytes())==d
    selected=get(CP/"selection.json");events=[json.loads(line) for line in (CP/"events.jsonl").read_bytes().splitlines()]
    scenarios={};artifacts=defaultdict(dict);evidence={};locks={}
    for ep,s in sorted(selected.items()):
        task,method,seed=ep.split("|");logs=[r for r in events if r["episode"]==ep];assert logs[-1]==s["last"]
        traj=VIBE/"episodes/python"/task/method/seed/(task+".traj.json");locks[ep]=sha(traj.read_bytes())
        bound,witness=test_evidence(get(traj)["messages"],logs);evidence[ep]=witness
        state_order=[];seen=set();compressed={};origin={}
        for i,r in enumerate(logs):
            h=r["sha"];b=raw_patch(h)
            assert len(b)==r["size"]
            compressed[h]=(CP/"patches"/(h+".patch.gz")).stat().st_size
            if h not in seen:
                state_order.append(dict(sha=h,bytes=len(b),gzip_bytes=compressed[h],at=r["at"],request=r["request_count"],i=i))
                seen.add(h)
            if h in artifacts[task]:assert raw_patch(h)==b
            artifacts[task][h]=dict(bytes=len(b),gzip_bytes=compressed[h])
        one=logs[-1]["sha"] if logs else None
        first=next((r["sha"] for r in logs if r["size"]),None)
        scenarios[ep]=dict(choices=dict(last=one,first_nonempty=first,visible_pass=bound,one_final_available=one),
            events=logs,unique=state_order,left_truncated=s["left_truncated"],size_journal=sum(len((json.dumps(r)+"\n").encode()) for r in logs))
    put(D/"selection.json",scenarios);put(D/"universe.json",artifacts);put(D/"selftest-evidence.json",evidence)
    put(D/"lock.json",dict(inputs={f:sha((D/f).read_bytes()) for f in ("PROTOCOL_RU.md","select_states.py","selection.json","universe.json","selftest-evidence.json")},
                source_seal=sha((CP/"sealed.json").read_bytes()),traj_sha=locks))
    print([(k,len(v)) for k,v in artifacts.items()],[(k,sum(x["bound_sha"] is not None for x in a)) for k,a in evidence.items()])
if __name__=="__main__":main()
