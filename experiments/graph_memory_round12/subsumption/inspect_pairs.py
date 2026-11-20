"""Independently re-read the source receipts of all five downstream decisions."""
from replay import D,EXT,read,save,parser,sha
import json,re
def main():
    roster={r["iid"]:r for r in read(EXT/"roster.json")}
    rows=[]
    for r in read(D/"decisions.gz"):
        if r["arm"]!="session|same_scope":continue
        meta=roster[r["iid"]];blob=(parser.V/"benchmark"/meta["file"]).read_bytes()
        assert sha(blob)==meta["sha"]
        msgs=json.loads(blob)["messages"];evidence=[];between=[]
        for step in range(r["previous"],r["step"]+1):
            m=msgs[step]
            if m.get("role")!="assistant":continue
            for tc in m.get("tool_calls") or []:
                arg=json.loads(tc["function"]["arguments"]);cmd=arg.get("command")
                if not isinstance(cmd,str):continue
                if step in (r["step"],r["previous"]):
                    resp=next(n for n in msgs[step+1:] if n.get("tool_call_id")==tc["id"])
                    evidence.append(dict(step=step,cmd=cmd,rc=resp["extra"]["returncode"],
                      output_hash=sha(resp["extra"]["raw_output"].encode()),bytes=len(resp["extra"]["raw_output"].encode())))
                else:
                    path=r["query"]["scope"]
                    refs=path in cmd
                    between.append(dict(step=step,kind=cmd.strip().split(maxsplit=1)[0][:40],mentions_path=refs,
                        possible_write=bool(re.search(r"(?:write_text|write_bytes|apply_patch|sed\s+-i|cat\s*>|open\([^\n]*?['\"]w|write\()",cmd)),
                        sha256=sha(cmd.encode())))
        assert evidence[0]["rc"]==1 and evidence[0]["bytes"]==0
        assert evidence[1]["rc"]==(1 if r["actual"]=="empty" else 0)
        rows.append(dict(iid=r["iid"],source=meta["upstream"],outcome=r["actual"],endpoints=evidence,intervening=between))
    save("pair-audit.json",rows)
if __name__=="__main__":main()
