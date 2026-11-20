"""Describe the final visible pytest summary independently of the frozen selector or any hidden result."""
from select_states import *
def main():
    evidence=get(D/"selftest-evidence.json");rows=[]
    for ep,recs in evidence.items():
        iid,method,seed=ep.split("|");traj=VIBE/"episodes/python"/iid/method/seed/(iid+".traj.json")
        msgs=get(traj)["messages"]
        outputs={m.get("tool_call_id"):m.get("extra",{}) for m in msgs if m.get("role")=="tool"}
        for r in recs:
            raw=outputs[r["action"]]["raw_output"]
            assert sha(raw.encode())==r["output_sha"]
            lines=[s.strip() for s in raw.splitlines() if re.search(r"\b\d+ (?:passed|failed|errors?)\b",s,re.I)]
            summary=lines[-1][:450] if lines else None
            counts={k:int(v) for v,k in re.findall(r"\b(\d+) (passed|failed|errors?|skipped|warnings?)\b",summary or "",re.I)}
            rows.append(dict(episode=ep,action=r["action"],raw_output_sha=r["output_sha"],shell_rc=r["rc"],command=r["command"],
                             last_visible_pytest_summary=summary,parsed_counts=counts,
                             eligible_under_frozen_rule=r["bound_sha"] is not None))
    put(D/"visible-test-summaries.json",rows)
if __name__=="__main__":main()
