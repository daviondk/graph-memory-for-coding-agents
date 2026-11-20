"""Reconcile every successful native server call (including format errors) with one isolated episode."""
import csv
import json
import os
from pathlib import Path

HERE=Path(__file__).resolve().parent
PROTOCOL=json.loads(Path(os.environ.get("VIBE_SOLVER_PROTOCOL",HERE/"prospective_27b.json")).read_text(encoding="utf8"))
ROOT=Path(os.environ["VIBE_RELEASE"])
RUNS=ROOT/"outputs"/PROTOCOL["runs_subdir"]
source=Path(os.environ.get("VIBE_27B_REQUEST_LOG","D:/CodexResearch/x20-qwen38-27b/requests.jsonl"))
output=HERE/("in_loop" if PROTOCOL["runs_subdir"]=="pilot_in_loop" else "qwen38_27b")
output.mkdir(exist_ok=True)
events=[json.loads(s) for s in source.read_text(encoding="utf8").splitlines() if s.strip()]
calls=[]
episodes=[]
seen=set()
for t in PROTOCOL["targets"]:
    iid=t["instance_id"]
    for k in PROTOCOL["planned_seeds"]:
        for arm in PROTOCOL["methods"]:
            sd=RUNS/"python"/iid/arm/f"seed{k}"
            meta=json.loads((sd/"result.json").read_text(encoding="utf8"))
            tr=json.loads((sd/f"{iid}.traj.json").read_text(encoding="utf8"))
            # Exactly one model worker ran at a time, and timestamps are from the same Windows host clock.
            matched=[x for x in events if x.get("http_status")==200 and x["replicate"]==k and meta["start_ts"]<=x["epoch"]<=meta["end_ts"]]
            assert len(matched)==tr["info"]["model_stats"]["api_calls"],(iid,arm,k,len(matched),tr["info"]["model_stats"])
            reported={m["extra"]["response"]["id"]:m["extra"]["response"]["usage"] for m in tr["messages"] if m.get("extra",{}).get("response",{}).get("usage")}
            actual={x["id"]:x["usage"] for x in matched}
            assert set(reported)<=set(actual) and not(seen&set(actual))
            for key in reported:
                assert [reported[key][n] for n in ("prompt_tokens","completion_tokens")]==[actual[key][n] for n in ("prompt_tokens","completion_tokens")]
            seen.update(actual)
            for idx,x in enumerate(matched,1):
                assert x["max_output"]==PROTOCOL["max_new_tokens_per_call"] and x["usage"]["completion_tokens"]<=x["max_output"] and x["temperature"]==PROTOCOL["temperature"]
                calls.append(dict(target=iid,arm=arm,seed=k,call=idx,response_id=x["id"],prompt_sha256=x["message_sha256"],
                    format_error=x["id"] not in reported,prompt_tokens=x["usage"]["prompt_tokens"],completion_tokens=x["usage"]["completion_tokens"],finish_reason=x["finish"]))
            episodes.append(dict(target=iid,arm=arm,seed=k,calls=len(matched),format_errors=len(matched)-len(reported),
                prompt_tokens=sum(x["usage"]["prompt_tokens"] for x in matched),completion_tokens=sum(x["usage"]["completion_tokens"] for x in matched)))
assert len(episodes)==len(PROTOCOL["methods"])*len(PROTOCOL["targets"])*len(PROTOCOL["planned_seeds"])
with (output/"episode_calls.csv").open("w",encoding="utf8",newline="") as f:
    writer=csv.DictWriter(f,fieldnames=list(calls[0]));writer.writeheader();writer.writerows(calls)
summary={"method":"Unique window of one solver in flight, matching replicate, all saved response IDs & usage cross-checked. Format errors are calls missing a normal recorded mini-SWE-agent response.","by_episode":episodes}
(output/"exact_usage.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf8")
