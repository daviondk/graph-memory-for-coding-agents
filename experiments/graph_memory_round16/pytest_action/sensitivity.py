"""Post-hoc analysis of evidence location and scope veto. Does not call a model or alter its recorded actions."""
import json,gzip,sys
from pathlib import Path
D=Path(__file__).resolve().parent;R=D.parents[1]/"graph_memory_round15/test_receipts";sys.path.insert(0,str(R))
from receipt_policy import terminal
def main():
    items=json.loads(gzip.decompress((D/"assignment.gz").read_bytes())); scored={s["uid"]:s for s in json.loads((D/"actions-scored.json").read_bytes())}
    rows=[]
    for r in items:
        s=scored[r["uid"]];reports=[(i,terminal(line)[0]) for i,line in enumerate(r["visible"].splitlines()) if terminal(line)[0] not in ("no_evidence",)]
        a=s["actions"]["structured"];veto=r["query"]!=r["selector"] and a=="record_passing_edge"
        rows.append(dict(uid=r["uid"],stratum=r["design"],reports=reports,scope_veto_fired=veto,truth=s["audited"],
                         posthoc_action="queue_verification" if veto else a))
    data=dict(rows=rows,posthoc_correct=sum(r["truth"]==(r["posthoc_action"]=="record_passing_edge") for r in rows),
              non_terminal_evidence_in_unverified=[r for r in rows if r["stratum"]=="unverified" and any(k in ("pass","fail") for _,k in r["reports"])])
    (D/"sensitivity.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf8")
    print(data["posthoc_correct"],len(data["non_terminal_evidence_in_unverified"]))
if __name__=="__main__":main()
