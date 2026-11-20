"""Verify delivery, eviction, causal timing, exact native prompt overhead, and independent resolution."""
import csv
import json
import hashlib
import os
from pathlib import Path
import zipfile
from policy import digest,Delivery

HERE=Path(__file__).resolve().parent
protocol=json.loads((HERE/"protocol.json").read_text(encoding="utf8"))
cards=json.loads((HERE/"cards.json").read_text(encoding="utf8"))
ROOT=Path(os.environ["VIBE_RELEASE"])
RUNS=ROOT/"outputs"/protocol["runs_subdir"]
store=ROOT.parent/"solver-runtime"/"in_loop_transport"
raw=[json.loads(s) for s in (store/"intervention_events.jsonl").read_text(encoding="utf8").splitlines() if s.strip()]
attempts=[json.loads(s) for s in (HERE/"attempts.jsonl").read_text(encoding="utf8").splitlines()]
with (HERE/"episode_calls.csv").open(encoding="utf8") as f:
    expected_calls=list(csv.DictReader(f))
rows=[]
with zipfile.ZipFile(HERE/"transport_evidence.zip","w",zipfile.ZIP_DEFLATED,compresslevel=8) as z:
    z.write(store/"intervention_events.jsonl","intervention_events.jsonl")
    for row in attempts:
        iid=row["target"];arm=row["method"];seed=row["seed"]
        meta=json.loads((RUNS/"python"/iid/arm/f"seed{seed}"/"result.json").read_text(encoding="utf8"))
        events=[e for e in raw if e.get("iid")==iid and e.get("arm")==arm and str(e.get("seed"))==str(seed) and meta["start_ts"]<=e["epoch"]<=meta["end_ts"]]
        calls=[c for c in expected_calls if c["target"]==iid and c["arm"]==arm and int(c["seed"])==seed]
        assert len(events)==row["agent_calls"]==len(calls) and len({e["attempt"] for e in events})==1
        assert [e["response_id"] for e in events]==[c["response_id"] for c in calls]
        assert all(e["card_sha256"]==cards[iid]["card_sha256"] for e in events)
        seen=set();triggered=False;first=None;earliest=None
        for n,e in enumerate(events,1):
            assert e["request"]==n and e["http_status"]==200
            for new in e["new_events"]:
                assert new["tool_call_id"] not in seen
                seen.add(new["tool_call_id"]);assert len(seen)==new["index"]
                eligible=bool(new["path"]) if arm=="path_trigger" else new["index"]==3
                if eligible and earliest is None:earliest=(n,new)
            assert e["observed_total"]==len(seen)
            if e["injected"]:
                assert not triggered and earliest==(n,e["trigger"]) and not e["evicted"]
                triggered=True;first=e
                snapshot=store/"payloads"/e["payload_file"];payload=json.loads(snapshot.read_text(encoding="utf8"))
                before=payload["incoming"];after=payload["forwarded"]
                assert {k:v for k,v in before.items() if k!="messages"}=={k:v for k,v in after.items() if k!="messages"}
                assert before["messages"]==after["messages"][:-1]
                assert digest(before["messages"])==e["incoming_sha256"] and digest(after["messages"])==e["forwarded_sha256"]
                assert after["messages"][-1]=={"role":"user","content":"<relevant_experiences>\n"+cards[iid]["card"]+"\n</relevant_experiences>"}
                assert e["template_delta_tokens"]>0 and abs(e["native_count_difference"])<=1
                z.write(snapshot,"payloads/"+snapshot.name)
            else:
                assert e["incoming_sha256"]==e["forwarded_sha256"] and e["evicted"]==triggered
        assert bool(first)==bool(earliest)
        rows.append(dict(target=iid,method=arm,seed=seed,resolved=row["resolved"],calls=len(events),exposed=bool(first),
            trigger_request=first["request"] if first else None,tool_result_index=first["trigger"]["index"] if first else None,
            match_path=first["trigger"]["path"] if first else None,match_source=first["trigger"]["match_source"] if first else None,
            extra_prompt_tokens=first["template_delta_tokens"] if first else 0,card_content_tokens=first["card_content_tokens"] if first else 0,
            native_count_difference=first["native_count_difference"] if first else None,
            evicted_on_later_calls=sum(e["evicted"] for e in events),total_input_tokens=row["input_tokens"],total_output_tokens=row["output_tokens"]))
summary={"rows":rows,"policy_arms":{arm:{"episode_count":sum(r["method"]==arm for r in rows),"exposures":sum(r["exposed"] for r in rows if r["method"]==arm),
"resolved":sum(r["resolved"] for r in rows if r["method"]==arm),"extra_prompt_tokens":sum(r["extra_prompt_tokens"] for r in rows if r["method"]==arm)} for arm in protocol["methods"]}}
(HERE/"delivery.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf8")
print(summary["policy_arms"])
