from select_states import *
from statistics import median
def main():
    g=get(D/"grading-lock.json");assert g["complete"] and g["input_lock"]==sha((D/"lock.json").read_bytes())
    for p,h in g["receipts"].items():assert sha((D/p).read_bytes())==h
    selected=get(D/"selection.json");states=get(D/"universe.json");witness=get(D/"selftest-evidence.json");results={};costs=Counter()
    all_bytes={};per_task={};totals=defaultdict(Counter);timeline=[]
    for task,hs in states.items():
        per_task[task]=0
        for h in hs:
            r=get(D/"grades"/task/h/"grade.json");assert r["task"]==task and r["sha"]==h
            for f,d in r["outputs"].items():assert sha((D/"grades"/task/h/f).read_bytes())==d
            if r["source_result"]:assert sha(Path(r["source_result"]).read_bytes())==r["source_result_sha"]
            if r["unit_log"]:costs["pairs_with_real_unit_log"]+=1
            costs["native_fresh"]+=not r["reused"];costs["native_grade_reused_identical_bytes"]+=r["reused"]
            costs["unique_task_state_pairs"]+=1
            per_task[task]+=r["resolved"]
            b=raw_patch(h);all_bytes[h]=len(b)
            costs["pair_dedup_bytes"]+=len(b);costs["pair_dedup_gzip"]+=hs[h]["gzip_bytes"]
    for ep,s in selected.items():
        task,method,seed=ep.split("|")
        logs=s["events"];r13=get(CP/"grading"/task/method/"result.json")
        def lookup(h):return get(D/"grades"/task/h/"grade.json") if h else None
        validators=[];runs=[]
        for i,e in enumerate(logs):
            row=lookup(e["sha"]);status=row["resolved"]
            validators.append(status);costs["every_poll_bytes"]+=e["size"];costs["every_poll_gzip"]+=states[task][e["sha"]]["gzip_bytes"]
            if not runs or runs[-1]["sha"]!=e["sha"]:
                runs.append(dict(sha=e["sha"],bytes=e["size"],resolved=status,first=i+1,last=i+1,first_seconds=round(e["at"]-logs[0]["at"],3),
                                  first_relative_proxy_request=e["request_count"]-logs[0]["request_count"],first_global_proxy_request=e["request_count"]))
            else:runs[-1]["last"]=i+1
            timeline.append(dict(episode=ep,index=i+1,elapsed=e["at"]-logs[0]["at"],global_request_count=e["request_count"],sha=e["sha"],resolved=status))
        choices={}
        for pol,h in s["choices"].items():
            selected_row=lookup(h)
            r=selected_row["resolved"] if selected_row else None
            choices[pol]=dict(sha=h,resolved=r,status=selected_row["status"] if selected_row else "abstain")
            totals[pol]["resolved"]+=r is True;totals[pol]["answered"]+=r is not None
            totals[pol]["abstain"]+=r is None
        assert choices["last"]["sha"]==choices["one_final_available"]["sha"]==r13["selected_sha"]
        assert choices["last"]["resolved"]==r13["resolved"]
        totals["official_submission"]["resolved"]+=bool(r13["official_resolved"]);totals["official_submission"]["answered"]+=1
        totals["oracle_any_passing"]["resolved"]+=any(validators);totals["oracle_any_passing"]["answered"]+=1
        first=next((j for j,x in enumerate(validators) if x),None);stop=logs[-1];first_evt=logs[first] if first is not None else None
        stats=dict(polls=len(logs),unique=len({x["sha"] for x in logs}),versions_in_order=runs,first_passing_poll=first+1 if first is not None else None,
            first_passing_seconds=round(first_evt["at"]-logs[0]["at"],3) if first_evt else None,
            first_passing_relative_request=first_evt["request_count"]-logs[0]["request_count"] if first_evt else None,
            remaining_observed_seconds_after_first_pass=round(stop["at"]-first_evt["at"],3) if first_evt else None,
            remaining_proxy_requests_after_first_pass=stop["request_count"]-first_evt["request_count"] if first_evt else None,
            later_lost=any(not x for x in validators[first+1:]) if first is not None else None,
            remained_to_end=all(validators[first:]) if first is not None else None,left_truncated=s["left_truncated"],
            sampled_span_seconds=round(stop["at"]-logs[0]["at"],3),choices=choices,official_submission_resolved=r13["official_resolved"],
            visible_test_mentions=len(witness[ep]),visible_pass_summary_zero_code=sum(r['rc']==0 and r['summary_pass'] for r in witness[ep]))
        results[ep]=stats
        costs["last_only_bytes"]+=stop["size"];costs["last_only_gzip"]+=states[task][stop["sha"]]["gzip_bytes"]
    costs["distinct_byte_payloads_any_task"]=len(all_bytes);costs["physical_patch_raw_unique"]=sum(all_bytes.values())
    costs["physical_patch_gzip_unique"]=sum((CP/"patches"/(h+".patch.gz")).stat().st_size for h in all_bytes)
    costs["physical_events_jsonl_bytes"]=(CP/"events.jsonl").stat().st_size
    put(D/"results.json",dict(episodes=results,totals=totals,cost=costs,passing_unique_states=per_task))
    put(D/"timeline.json",timeline)
    put(D/"verification.json",dict(source_grading_lock=sha((D/"grading-lock.json").read_bytes()),analysis=sha(Path(__file__).read_bytes()),summary=sha((D/"results.json").read_bytes()),
               timeline=sha((D/"timeline.json").read_bytes()),checked_terminal_R13=4,checked_native_result_files=len(g["receipts"])))
    print(dict(totals));print(dict(costs))
    for k,s in results.items():print(k,s["polls"],[(r["first"],r["last"],r["resolved"]) for r in s["versions_in_order"]],s["first_passing_seconds"],s["remaining_observed_seconds_after_first_pass"])
if __name__=="__main__":main()
