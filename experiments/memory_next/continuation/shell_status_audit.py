"""Post-design measurement of outer exit-code masking in predecessor tests; never used in the treatment."""
import csv
import re
from pathlib import Path
from handoff import ROOT,items,ev,is_test,normalize,read,sha,write_json

NEG=re.compile(r"\b(?:[1-9]\d*\s+(?:failed|errors?)\b|(?:FAILED|ERROR)\s+(?:tests?[/\\]|test[_\w.]|[\w.]+::)|FAILED\s*\((?:errors|failures)\s*=)",re.I)
def run():
    rows=[]
    for iid in sorted({i for i,arm in read(ROOT/"assignments.json")}):
        folder=ROOT/"handoffs"/iid
        f=folder/"previous_actions.jsonl"
        for a in items(f):
            e=ev(a)
            if not e["executable"] or not is_test(e["cmd"]):continue
            raw=a["stdout"]+"\n"+a["stderr"]
            m=NEG.search(raw)
            rows.append({"id":iid,"turn":e["turn"],"index":e["index"],"outer_rc":e["status"],"pipe_character":"|" in e["cmd"],
                         "raw_output_failure_marker":bool(m),"in_extra_journal":f't{e["turn"]}.{e["index"]} shell exit' in (folder/"manifest_only.txt").read_text(encoding="utf-8"),
                         "cmd_sha256":sha(e["cmd"].encode()),"output_sha256":sha(raw.encode())})
    with (ROOT/"shell_status_audit.csv").open("w",encoding="utf-8",newline="") as fp:
        w=csv.DictWriter(fp,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    result={"invocations":len(rows),"with_pipe":sum(r["pipe_character"] for r in rows),
            "outer_zero_with_failure_marker":sum(r["outer_rc"]==0 and r["raw_output_failure_marker"] for r in rows),
            "zero_and_failure_in_journal":sum(r["outer_rc"]==0 and r["raw_output_failure_marker"] and r["in_extra_journal"] for r in rows)}
    write_json(ROOT/"shell_status_audit.json",result)
    print(result)
if __name__=="__main__":run()

