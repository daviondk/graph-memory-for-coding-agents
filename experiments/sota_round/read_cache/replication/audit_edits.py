"""Independently confirm actual post-edit file bytes in every issued write-through hit."""
import argparse
import json
from pathlib import Path
from analyze import records
from replay import HERE,turns,sha,visible


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--data",type=Path,default=Path("D:/CodexResearch/x20-swe-context"))
    root=ap.parse_args().data
    hist={h["sid"]:h for h in records("histories.jsonl.gz")}
    checks=[]
    for q in records("queries.jsonl.gz"):
        hit=q["arms"][-1]
        if not hit or not hit[3]:
            continue
        sid=q["sid"];raw=(root/"traces"/(sid+".jsonl")).read_bytes()
        assert sha(raw)==hist[sid]["sha256"]
        bs=list(turns(raw))
        b,slot,state,es,pred=hit
        def result(batch,index):
            calls,obs,_=bs[batch]
            return obs[calls[index][2]]
        old=result(b,slot);new=result(q["b"],q["slot"])
        content=old[1]["file"]["content"]
        for step in es:
            calls,obs,_=bs[step];assert len(calls)==1
            op,inp,tid,_=calls[0];assert op=="Edit" and visible(obs[tid])[0]=="success"
            content=content.replace(inp["old_string"],inp["new_string"],-1 if inp.get("replace_all") else 1)
        visible_text=visible(new)[1]
        matches=content==new[1]["file"]["content"] and sha(visible_text.encode())==pred
        assert matches and state=="correct"
        checks.append({"sid":sid,"repo":hist[sid]["repo_proxy"],"source_step":b,"edit_steps":es,
                       "target_step":q["b"],"path":q["key"][0],"visible_bytes":len(visible_text.encode()),
                       "actual_file_sha256":sha(content.encode()),"observed_response_sha256":pred})
    (HERE/"edit_checks.json").write_text(json.dumps(checks,indent=2),encoding="utf8")


if __name__=="__main__":
    main()
