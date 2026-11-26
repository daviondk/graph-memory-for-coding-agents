"""Read private scoring fields only after selection. Persist counts and IDs, never code."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq

from experiment import ROOT, WORK, NAT, read, signed, sha, dump


def h(s):
    return hashlib.sha256(s.encode("utf8")).hexdigest()


def main():
    raw = Path("D:/CodexResearch/x20-r31-handoff")
    source_info = raw / "files.json"
    edit_ready = WORK / "graph_memory_round38/edit_ready"
    assert sha(source_info) == signed(edit_ready,"input-seal.json")["source_manifest"]
    frozen = read(ROOT/"scored.json.gz")
    assert sha(ROOT/"scored.json.gz") == read(ROOT/"results.json")["forecasts"]
    wanted = defaultdict(dict)
    for row in frozen:
        wanted[row["rid"]][row["receipt"]] = row
    views = signed(edit_ready, "visible.json.gz")
    plans = signed(NAT, "plans.json.gz")
    totals = Counter()
    by_row = []
    hashed_runs = {}
    for shard in read(source_info)["events"]:
        file = raw / shard["file"]
        assert sha(file) == shard["sha"]
        for batch in pq.ParquetFile(file).iter_batches(columns=["run_id","event_index","event_json"],batch_size=384):
            for idx,(run,at) in enumerate(zip(batch.column(0).to_pylist(), batch.column(1).to_pylist())):
                if run not in hashed_runs:
                    hashed_runs[run]=h(run)
                rid=hashed_runs[run]
                if rid not in wanted or at not in wanted[rid]:
                    continue
                row = wanted[rid].pop(at)
                obs=json.loads(batch.column(2)[idx].as_py())["raw"]["observation"]
                assert obs["command"] == "str_replace" and not obs["is_error"]
                before=obs["old_content"].split("\n")
                after=obs["new_content"].split("\n")
                addresses={n:dig for n,dig,_,_ in views[rid][str(row["view"])]}
                blocks=plans[rid][str(row["event"])]
                cnt=Counter(receipts=1,confirmed_delta=int(len(after)-len(before)==row["delta"]))
                for i in row["eligible"]:
                    path,low,high,*_ = blocks[i]
                    assert path == row["path"]
                    for n in range(low,high+1):
                        new_n = n+row["delta"] if n>row["end"] else n
                        prior = 0<n<=len(before) and h(before[n-1]) == addresses[n]
                        current = 0<new_n<=len(after) and h(after[new_n-1]) == addresses[n]
                        cnt["lines"]+=1
                        cnt["prior_mismatch"]+=int(not prior)
                        cnt["post_mismatch"]+=int(not current)
                        cnt["new_mismatch"]+=int(prior and not current)
                        if not prior and 0<n<=len(before):
                            line=before[n-1]
                            transforms={"rstrip":line.rstrip(), "strip":line.strip(),"tab4":line.expandtabs(4),"tab8":line.expandtabs(8),"tab4_strip":line.expandtabs(4).rstrip(),"tab8_strip":line.expandtabs(8).rstrip()}
                            matched=sorted(k for k,v in transforms.items() if h(v)==addresses[n])
                            cnt["explained:" + ",".join(matched) if matched else "unexplained"]+=1
                        if row["range_reuse"] and i in row["old"]:
                            cnt["reused_selected_lines"]+=1
                            cnt["reused_selected_post_mismatch"]+=int(not current)
                        if i in row["old"]:
                            cnt["selected_lines"]+=1
                            cnt["selected_post_mismatch"]+=int(not current)
                        if row["range_reuse"]:
                            cnt["reuse_lines"]+=1
                            cnt["reuse_post_mismatch"]+=int(not current)
                totals.update(cnt)
                by_row.append([rid,at,dict(cnt)])
    assert not any(wanted.values())
    dump(ROOT/"audit_strict_rows.json.gz",sorted(by_row))
    dump(ROOT/"audit_strict.json",dict(counts=dict(totals),checks=sha(ROOT/"audit_strict_rows.json.gz"),
             raw_manifest=sha(source_info),sealed=sha(ROOT/"scored.json.gz")))
    print(dict(totals))


if __name__ == "__main__":
    main()

