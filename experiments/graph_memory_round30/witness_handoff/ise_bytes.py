"""Check physical contents of original output messages and the actual path argument used, with no command execution."""
from collections import Counter
from inventory import P,D,SPL,RISK,extra,allow,get,save,h
from hashlib import sha256
from pathlib import PurePosixPath
import json
def main(panel="ise"):
    mask={r["id"]:r["events"] for r in get(P/(panel+"-events.json.gz"))};counts=Counter();aliases=Counter();eligible_alias=Counter()
    for f in sorted(SPL.glob("trajectories-*.jsonl")):
        with f.open("rb") as inp:
            for line in inp:
                r=json.loads(line);q=r["session_id"]
                prompt=" ".join(str(s["natural_language_intent"]) for s in r["source_intents"])
                if not allow.search(prompt) or RISK.search(prompt) or extra.search(prompt):continue
                events={a["id"]:a for a in mask.get(q,[])};bycall={}
                for k,m in enumerate(r["messages"]):
                    if m["role"]=="assistant":
                        for a in m.get("tool_calls",[]):
                            fn=a.get("function",{})
                            if fn.get("name")!="read":continue
                            try:
                                arg=fn["arguments"];arg=json.loads(arg) if isinstance(arg,str) else arg
                                if isinstance(arg,dict):bycall[a["id"]]=arg
                            except (TypeError,ValueError):continue
                    elif m["role"]=="tool" and m.get("name")=="read" and m.get("success") and m.get("tool_call_id") in bycall:
                        arg=bycall[m["tool_call_id"]];which=next((z for z in ["path","file_path","filePath","file"] if isinstance(arg.get(z),str)),None);aliases[str(which)]+=1
                        path=arg.get(which) if which else None;txt=m["content"]
                        if isinstance(path,str) and isinstance(txt,str) and path.startswith("/workspace/") and PurePosixPath(path).suffix.lower() in {".md",".txt",".csv",".tsv",".rst"} and not any(v.search(s) for v in (extra,RISK) for s in (path,txt)):eligible_alias[str(which)]+=1
                        if k in events:
                            ff=events[k];assert h(path)==ff["path"];offset=int(arg.get("offset",1))
                            actual=txt.splitlines()
                            for i,d,b in ff["lines"]:
                                s=actual[i-offset].encode();assert len(s)==b and sha256(s).hexdigest()==d;counts["verified_line_receipts"]+=1
                            counts["verified_events"]+=1
                if events:counts["verified_trajectories"]+=1
    assert counts["verified_line_receipts"]==get(D/(panel+"-inventory.json"))["counts"]["eligible_line_receipts"]
    rec=dict(counts=counts,all_successful_read_aliases=aliases,benign_text_aliases=eligible_alias);save(D/(panel+"-byte-audit.json"),rec);print(rec)
if __name__=="__main__":
    import sys
    main(sys.argv[1] if len(sys.argv)>1 else "ise")

