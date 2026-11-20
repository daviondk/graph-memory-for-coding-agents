"""Audit observed source actions and summarize the complete pairings without target answers."""
import json
import platform
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from fetch_history import BASE, META, PIN
from run_stage import official
from methods import METHODS, TEST_COMMAND, TEST_PASS, READ
from memory_systems.demo import EchoMemorySystem
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parent


def verify_history(audit, item):
    sid=item["source_session_id"]
    target=audit["instance_id"]
    repo=audit["repo"].replace("/","__")
    assert sid.rsplit("-",1)[0].casefold()==repo.casefold() and int(sid.rsplit("-",1)[1])<int(target.rsplit("-",1)[1])
    path=BASE/"benchmark"/"history"/audit["language"]/repo/sid/(sid+".traj.json")
    msgs,_,_=official._load_trajectory(path)
    steps=EchoMemorySystem()._iter_steps([official._strip_message(m) for m in msgs])
    if audit["method"]=="action_receipt":
        index=int(item["id"].split("::step")[1])
        s=steps[index]
        assert str(s["returncode"])=="0" and s["output"].strip() and s["command"].strip()
        if audit["selected_kind"]=="observed_test":
            assert TEST_COMMAND.search(s["command"]) and TEST_PASS.search(s["output"])
            assert not re.search(r"[|;]",s["command"])
        else:
            assert audit["selected_kind"]=="observed_read" and READ.search(s["command"])


def main():
    allowed_cols=["instance_id","language","repo"]
    roster={r["instance_id"]:r for r in pq.read_table(BASE/"benchmark"/"test.parquet",columns=allowed_cols).to_pylist()}
    assert len(roster)==111
    info=json.loads((META/"source-manifest.json").read_bytes())
    files={entry["rfilename"]:entry["size"] for entry in info["siblings"] if entry["rfilename"].endswith(".traj.json")}
    rows=[]
    coverage={}
    for q,entry in roster.items():
        repo=entry["repo"].replace("/","__")
        prior=[n for n in files if n.split("/")[2]==repo and int(n.split("/")[3].rsplit("-",1)[1])<int(q.rsplit("-",1)[1])]
        coverage[q]=[n for n in prior if files[n]<=64_000_000]
    run=BASE/"outputs"/"memory"
    with ZipFile(ROOT/"stage_outputs.zip","w",compression=ZIP_DEFLATED,compresslevel=6) as z:
        for method in METHODS:
            for q,entry in sorted(roster.items()):
                out=run/method/entry["language"]/q
                meta=json.loads((out/"memory.json").read_bytes())
                audit=json.loads((BASE/"memory-stage-audit"/method/(q+".json")).read_bytes())
                assert meta["num_histories_fed"]==audit["source_histories"]==len(coverage[q])
                assert len(meta["retrieved"])==audit["retrieved"] and meta["method"]==method
                if meta["retrieved"] and method=="action_receipt":
                    verify_history(audit,meta["retrieved"][0])
                rows.append(audit)
                for fname in ["memory.txt","memory.json"]:
                    z.write(out/fname,f"{method}/{entry['language']}/{q}/{fname}")
    (ROOT/"stage_rows.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows),encoding="utf8")
    summary={"targets":len(roster),"repos":len(set(r["repo"] for r in roster.values())),
             "history_in_release":len(files),"eligible_unique_fed":len(set().union(*map(set,coverage.values()))),
             "total_target_history_pairs":sum(map(len,coverage.values())),"source_pin":PIN,
             "official_parser_sha256":json.loads((ROOT/"upstream_sha256.json").read_bytes())["scripts/run_memory.py"],
             "versions":{"python":sys.version,"platform":platform.platform(),"pandas":pd.__version__,"pyarrow":pa.__version__},
             "by_method":{}}
    for method in METHODS:
        entries=[a for a in rows if a["method"]==method]
        agg={}
        for k in ["source_histories","source_messages","stored_records","stored_text_bytes","retrieved","skipped_sessions","words_with_header","wall_seconds"]:
            values=[a[k] for a in entries]
            agg[k]={"sum":sum(values),"mean":st.mean(values),"median":st.median(values),"range":[min(values),max(values)]}
        agg["selected_source_kind"]=dict(Counter(a["selected_kind"] for a in entries if a["retrieved"]))
        summary["by_method"][method]=agg
    (ROOT/"results.json").write_text(json.dumps(summary,indent=2),encoding="utf8")
    print("verified",len(rows),"official outputs;",summary["total_target_history_pairs"],"causal pairs per method")
    for method,summary in summary["by_method"].items():
        print(method,[(name,summary[name]["sum"],round(summary[name]["mean"],2)) for name in
                      ("retrieved","stored_records","stored_text_bytes","words_with_header","wall_seconds")],
              summary["selected_source_kind"])


if __name__=="__main__":
    main()
