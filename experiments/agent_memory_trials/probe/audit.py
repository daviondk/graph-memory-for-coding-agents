"""Post-freeze integrity checks. Read-only on the frozen dataset and main results."""
import collections
import datetime as dt
import json
from pathlib import Path

from study import ARMS, ROOT, execute, fetch_run, read, verify


def parsed_time(value):
    return dt.datetime.fromisoformat(value)


def audit():
    verify()
    plan = read("allocation.json")
    cases = read("targets_hidden.json")
    scores = read("scores.json")
    resources = read("resources.json")
    freeze_at = parsed_time(read("freeze.json")["freeze_utc"])
    starts = [parsed_time(r["started_utc"]) for r in resources]
    ends = [parsed_time(r["ended_utc"]) for r in resources]
    assert min(starts) > freeze_at
    assert max(parsed_time(r["ended_utc"]) for r in resources if r["stage"]==1) < min(parsed_time(r["started_utc"]) for r in resources if r["stage"]==2)
    assert len(scores)==36 and len(cases)==12 and len(plan)==12
    assert set((a,c) for a in ARMS for c in cases) == {(r["arm"],r["case"]) for r in scores}
    assert collections.Counter(r["stable"] for r in cases.values()) == {True:6,False:6}
    for case in cases.values():
        assert len({tuple(execute(case["family"],m,x) for x in case["heldout"]) for m in range(4)}) == 4
    for row in plan:
        st1, st2 = fetch_run(1,row["id"]), fetch_run(2,row["id"])
        services1, services2 = [json.loads(run["prompt"].split("Services follow.\n")[1]) for run in (st1,st2)]
        assert [a["id"] for a in services1] == [a["id"] for a in services2] == row["cases"]
        for ser1,ser2 in zip(services1,services2):
            case = cases[ser1["id"]]
            result = next(r for r in scores if r["id"]==row["id"] and r["case"]==ser1["id"])
            assert "pending_application_inputs" not in ser1 and "only_observation_on_current_release" not in ser1
            assert ser2["only_observation_on_current_release"] == result["observation"]
            assert case["heldout"] == ser2["pending_application_inputs"] == result["heldout"]
            assert ser2["manual"] == ser1["manual"]
            assert ("one_archived_call_from_an_earlier_release" in ser1) == (row["arm"] != "fresh")
            if result["status"] == "executed":
                observed = result["observation"]
                assert execute(case["family"],case["mode"],observed["input"]) == observed["output"]
            assert [execute(case["family"],case["mode"],x) for x in case["heldout"]] == result["expected"]
    print(json.dumps({"verified":True,"freeze_utc":freeze_at.isoformat(),"first_model_request_utc":min(starts).isoformat(),
                      "last_model_end_utc":max(ends).isoformat(),"total_elapsed_s":(max(ends)-min(starts)).total_seconds(),
                      "n_cases":len(cases),"n_scores":len(scores),"n_model_requests":2*len(plan),"n_model_attempts":len(resources)},indent=2))


if __name__ == "__main__":
    audit()
