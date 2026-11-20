"""Grade only the final prespecified R13 checkpoint, after the complete R12 grading and sealed selection."""
from pathlib import Path
import gzip,hashlib,json,shutil,sys,time
HERE=Path(__file__).resolve().parent;CP=HERE.parent;R12=CP.parents[1]/"graph_memory_round12/vibe/grading"
sys.path.insert(0,str(R12))
from grade import specs,ids,methods,run_eval,load,put,sha,done
PRIVATE=Path("D:/CodexResearch/x20-r13-evaluator-inputs")

def grade_all(wait):
    while not ((CP/"sealed.json").is_file() and all(done(i,m).is_file() for i in ids for m in methods+("gold","marker"))):
        if not wait:raise RuntimeError("Waiting for all R12 official results and final R13 seal")
        time.sleep(8)
    for f,d in load(CP/"sealed.json").items():assert sha((CP/f).read_bytes())==d
    assignment=load(CP/"assignment.json")
    assert assignment["protocol"]==sha((CP/"PROTOCOL_RU.md").read_bytes()) and assignment["observer"]==sha((CP/"observe.py").read_bytes())
    selected=load(CP/"selection.json")
    assert set(selected)=={f"{i}|{m}|seed0" for i in ids for m in methods}-set(assignment["excluded"])
    journal=[json.loads(line) for line in (CP/"events.jsonl").read_bytes().splitlines()]
    for k,sel in sorted(selected.items()):
        i,m,seed=k.split("|");assert seed=="seed0"
        official=load(done(i,m));last=sel["last"];e=[r for r in journal if r["episode"]==k]
        assert (e[-1] if e else None)==last
        out=HERE/i/m;out.mkdir(parents=True,exist_ok=True)
        record=out/"result.json"
        if record.exists():
            prev=load(record);assert prev["selected_sha"]==(last["sha"] if last else None)
            continue
        summary=dict(episode=k,method=m,instance=i,official_submitted_sha=official["patch_sha"],official_resolved=official["official"]["resolved"],
                     selected_sha=None,selected_bytes=None,reused=False,left_truncated=sel["left_truncated"],observations=sel["count"])
        if last is None:
            put(record,{**summary,"status":"no_observation","resolved":None});continue
        digest=last["sha"];b=gzip.decompress((CP/"patches"/(digest+".patch.gz")).read_bytes());assert sha(b)==digest and len(b)==last["size"]
        summary.update(selected_sha=digest,selected_bytes=len(b))
        # Reuse only the very same episode's true submission with local byte comparison.
        can_reuse=(digest==official["patch_sha"] and load(Path(official["official"]["seed_dir"])/"eval_input.json")[0]["patch"].encode()==b)
        if can_reuse:
            info=official["official"]
            origin=done(i,m).parent
            summary.update(reused=True,reuse_result_sha=sha(done(i,m).read_bytes()))
            native_src=origin/"native-report.json";unit_src=origin/"unit.log"
        else:
            wd=PRIVATE/i/m
            if wd.exists():raise RuntimeError(f"Unfinished private evaluator run at {wd}")
            wd.mkdir(parents=True)
            info=run_eval.evaluate_seed(run_eval.SeedRun(wd,i,b.decode("utf8")),specs,R12/"bridge.py",timeout=1800)
            native_src=wd/"eval_report.json"
            interim=load(native_src)["items"][0] if native_src.is_file() else {}
            unit_src=wd/interim.get("log_path","__no_unit_log__");origin=wd
        item=load(native_src)["items"][0] if native_src.is_file() else {}
        for f in ("eval_stdout.log","eval_stderr.log","container.log"):
            if (origin/f).is_file():shutil.copyfile(origin/f,out/f)
        if native_src.is_file():shutil.copyfile(native_src,out/"native-report.json")
        if unit_src.is_file():shutil.copyfile(unit_src,out/"unit.log")
        status="no_patch" if not b.strip() else "harness_error" if info.get("error") else "resolved" if info["resolved"] else "unresolved"
        summary.update(resolved=info.get("resolved",False),status=status,official_eval=info,unit_exit=item.get("exit_code"),
              passed_match=item.get("passed_match"),f2p=len(item.get("from_fail_to_pass",[])) if unit_src.is_file() else None,
              lost_p2p=len(item.get("failed_from_pass_to_pass",[])) if unit_src.is_file() else None,
              expected_f2p=len(specs[i]["FAIL_TO_PASS"]),expected_p2p=len(specs[i]["PASS_TO_PASS"]),
              raw_outputs={f.name:sha(f.read_bytes()) for f in out.iterdir() if f.is_file()})
        put(record,summary);print(k,status,len(b),"reused" if can_reuse else "native",flush=True)
    rows=[load(HERE/k.split("|")[0]/k.split("|")[1]/"result.json") for k in sorted(selected)]
    put(HERE/"results.json",dict(complete=True,n=len(rows),sealed_sha=sha((CP/"sealed.json").read_bytes()),rows=rows,
            solver_resolved=sum(r["official_resolved"] for r in rows),checkpoint_resolved=sum(r["resolved"] is True for r in rows),
            unavailable=sum(r["resolved"] is None for r in rows),source={str(f):sha(f.read_bytes()) for f in [__file__ and Path(__file__),R12/"grade.py",R12/"bridge.py",R12/"bin/docker"]}))
if __name__=="__main__":grade_all("--wait" in sys.argv)
