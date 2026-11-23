"""Verify stage receipts and score fixed tools, menu reachability, and individual paired actions."""
import collections
import gzip
import hashlib
import json
import math
import random
from menu import D,F,ARMS,LOCK,h,read,put,lock

METRICS=("patch_open","patch_in_menu","next_open","next_in_menu")
CONTRASTS=(("typed_union","flat_union"),("typed_union","view_graph"),("flat_union","view_graph"))

def aggregate(records):
    sums={}
    for key in METRICS+("valid","opened","new_visible_path_open","new_outside_view_graph_open"):
        eligible=[r[key] for r in records if r[key] is not None]
        sums[key]={"n":len(eligible),"yes":sum(eligible)}
    for key in ("bytes","prompt_tokens","completion_tokens","menu_path_bytes","payload_bytes"):
        sums[key]=sum(r[key] for r in records)
    sums["read_sources"]=dict(collections.Counter((r["read_source"] or "absent") for r in records))
    return sums

def pair(rows,first,second):
    out={"n":len(rows)}
    for key in ("sha","requested_path","opened_path"):
        out[key+"_changed"]=sum(r[first][key]!=r[second][key] for r in rows)
    for key in METRICS:
        diffs=[int(r[first][key])-int(r[second][key]) for r in rows if r[first][key] is not None]
        wins=diffs.count(1);losses=diffs.count(-1);n=len(diffs);t=wins+losses
        prob=None if not t else min(1,2*sum(math.comb(t,k) for k in range(min(wins,losses)+1))/(2**t))
        ci=None
        if n:
            rng=random.Random(20261121)
            sims=sorted(sum(rng.choices(diffs,k=n))/n for _ in range(10000))
            ci=[sims[249],sims[9749]]
        out[key]={"n":n,"wins":wins,"losses":losses,"ties":n-t,"delta":sum(diffs)/n if n else None,
                  "two_sided_exact_sign_p":prob,"descriptive_paired_bootstrap_95":ci}
    return out

def main():
    for name in ("assignment.json","action.lock.json","read.lock.json","blob.lock.json","truth.lock.json"):lock(D/name)
    assert h((F/"forecast.lock.json").read_bytes())==LOCK
    lock(F/"forecast.lock.json")
    prompts=read(D/"prompts.json.gz")
    actual=[json.loads(l) for l in (D/"model_calls.jsonl").read_bytes().splitlines()]
    models={r["sha"]:r for r in actual}
    assert len(actual)==len(models)==len(prompts)
    for sha,r in models.items():
        assert h(prompts[sha].encode())==sha and h(r["original_response"].encode())==r["response_sha"]
        response=json.loads(r["original_response"])
        assert r["usage"]==response["usage"] and r["model"]==response["model"]
        native=response["choices"][0]["message"].get("tool_calls") or []
        selection=None
        if len(native)==1 and native[0]["function"]["name"]=="read_file":
            selection=json.loads(native[0]["function"]["arguments"]).get("path")
        valid=selection in json.loads(prompts[sha])["tools"][0]["function"]["parameters"]["properties"]["path"]["enum"]
        assert r["valid"]==valid and r["path"]==(selection if valid else None)
    reads=read(D/"reads.json.gz")
    chosen={(r["id"],r["arm"]):r for r in reads}
    assert len(chosen)==len(reads)
    blobs={}
    for r in reads:
        if not r["opened"]:continue
        sha=r["sha256"]
        if sha not in blobs:
            blobs[sha]=gzip.decompress((D/"blobs"/(sha+".gz")).read_bytes())
        b=blobs[sha]
        assert h(b)==sha and len(b)==r["bytes"] and hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()==r["blob"]
    missing={(v["id"],v["arm"]) for v in read(D/"absent_reads.json") if v.get("verified_absent")}
    assert missing=={(r["id"],r["arm"]) for r in reads if r["path"] and not r["opened"]}
    inputs={x["id"]:x for rows in read(F/"frontier_inputs.json.gz").values() for x in rows}
    ranks={x["id"]:x["ranks"] for rows in read(F/"forecasts.json.gz").values() for x in rows}
    labels=read(D/"heldout.json.gz")
    cases=read(D/"menus.json.gz")
    logical=read(D/"logical_calls.json")
    links={(v["id"],v["arm"]):v["sha"] for v in logical}
    assert len(links)==len(cases)*len(ARMS)==len(chosen)
    by_case=[];status=collections.Counter()
    for q in cases:
        cid=q["id"];truth=labels[cid];pr=truth["pr"];f=inputs[cid];row={}
        assert pr["iid"]==q["iid"] and q["base"]==pr["base"]
        strict=truth["status"]=="strict_production_change"
        if strict:assert pr["strict"] and pr["base"]==pr["parent"] and pr["new_time"]>=pr["old_time"] and pr["prod"]
        status[truth["status"]]+=1
        for arm in ARMS:
            sha=links[cid,arm];r=chosen[cid,arm];m=models[sha];menu=q["menus"][arm]
            assert r["call"]==sha and m["path"]==r["path"] and (not m["valid"] or m["path"] in menu)
            assert r["base"]==q["base"] and set(menu)==set(ranks[cid][arm][:6]) and len(menu)==len(set(menu))==6
            picked=r["path"] if r["opened"] else None
            new= picked in f["frontier"] and picked not in f["viewed"]
            status_kind=truth["status"]
            row[arm]={"id":cid,"iid":q["iid"],"panel":q["panel"],"repo":q["repo"],"arm":arm,"sha":sha,
                      "requested_path":m["path"],"opened_path":picked,"valid":m["valid"],"opened":r["opened"],
                      "new_visible_path_open":new,"new_outside_view_graph_open":new and picked not in ranks[cid]["view_graph"],
                      "patch_open":picked in pr["prod"] if strict else None,"patch_in_menu":bool(set(menu)&set(pr["prod"])) if strict else None,
                      "next_open":picked in truth["next"] if truth["next"] else None,"next_in_menu":bool(set(menu)&set(truth["next"])) if truth["next"] else None,
                      "bytes":r["bytes"],"menu_path_bytes":sum(len(p.encode()) for p in menu),"payload_bytes":len(prompts[sha].encode()),
                      "prompt_tokens":m["usage"]["prompt_tokens"],"completion_tokens":m["usage"]["completion_tokens"],"read_source":r["source"],
                      "strict_status":status_kind}
        by_case.append(row)
    put(D/"outcomes_scored.json.gz",by_case)
    groups={"all":by_case,**{p:[r for r in by_case if r[ARMS[0]]["panel"]==p] for p in sorted({q["panel"] for q in cases})}}
    results={}
    for group,rows in groups.items():
        results[group]={"cases":len(rows),"projects":len({r[ARMS[0]]["repo"] for r in rows}),
                        "arms":{arm:aggregate([r[arm] for r in rows]) for arm in ARMS},
                        "pairs":{a+"_vs_"+b:pair(rows,a,b) for a,b in CONTRASTS}}
    resources={"actual_model_calls":len(actual),"logical_actions":len(reads),"real_read_attempts":len(reads),
               "actual_model_prompt_tokens":sum(r["usage"]["prompt_tokens"] for r in actual),
               "actual_model_completion_tokens":sum(r["usage"]["completion_tokens"] for r in actual),
               "native_cached_prompt_tokens":sum(r["usage"]["prompt_tokens_details"]["cached_tokens"] for r in actual),
               "model_elapsed_seconds_serial":sum(r["seconds"] for r in actual),"read_elapsed_seconds_summed":sum(r["seconds"] for r in reads),
               "actual_bytes_opened":sum(r["bytes"] for r in reads),"distinct_file_contents":len(blobs),"distinct_content_bytes":sum(map(len,blobs.values()))}
    put(D/"results.json",{"panels":results,"strict_status":status,"resources":resources})
    put(D/"verification.json",{"forecast_lock":LOCK,"stage_locks_verified":5,"prompt_sha_and_native_response_sha":len(models),
        "logical_calls_and_menu_limits":len(links),"successful_real_read_sha1_sha256_bytes":sum(r["opened"] for r in reads),
        "confirmed_absences":len(missing),"unique_tasks":len({q["iid"] for q in cases}),"outcome_lock":h((D/"truth.lock.json").read_bytes())})
    print("strict status",status,"resources",resources)
    for name,v in results.items():
        print(name,[(arm,[(k,v["arms"][arm][k]["yes"],v["arms"][arm][k]["n"]) for k in METRICS]) for arm in ARMS])
    print(results["all"]["pairs"],flush=True)

if __name__=="__main__":main()
