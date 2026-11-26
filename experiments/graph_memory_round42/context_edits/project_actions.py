"""Extract only visible old/new literal equality classes from known action events, not receipt bodies."""
from collections import defaultdict
import pyarrow.parquet as pq
from mechanism import tokens
from local import D,G,RAW,V,case_id,read,save,sha,signed,h,json


def main():
    assert sha(D/"PROTOCOL_RU.md")=="dc89853a2d52bde7a9177f4bd33531d30d5a6f8ea02d54dd33c217f6c153f047"
    events=signed(G,"selections.json.gz")
    desired=defaultdict(dict)
    for row in events:desired[row["run"]][row["at"]]=row
    seen={};hashes={}
    for src in read(RAW/"files.json")["events"]:
        file=RAW/src["file"];assert sha(file)==src["sha"]
        for batch in pq.ParquetFile(file).iter_batches(columns=["run_id","event_index","event_json"],batch_size=384):
            for j,(run,at) in enumerate(zip(batch.column(0).to_pylist(),batch.column(1).to_pylist())):
                if run not in hashes:hashes[run]=h(run)
                rid=hashes[run]
                if rid not in desired or at not in desired[rid]:continue
                row=desired[rid][at]
                # Never unpack new_content, old_content or any observation in this acquisition pass.
                act=json.loads(batch.column(2)[j].as_py())["raw"]["action"]
                assert act["command"]=="str_replace"
                assert h(act["path"].removeprefix("/testbed/").removeprefix("/workspace/"))==row["path"]
                old=act["old_str"];new=act["new_str"];left=tokens(old);right=tokens(new)
                assert len(left)==row["end"]-row["start"]+1 and len(right)-len(left)==row["delta"]
                key=case_id(row);assert key not in seen
                seen[key]=dict(old=left,new=right,bytes=len(old.encode())+len(new.encode()),raw_old_bytes=len(old.encode()))
    assert len(seen)==len(events)==2696
    save("action-lines.json.gz",seen)
    save("action-seal.json",dict(actions=sha(D/"action-lines.json.gz"),events=sha(G/"selections.json.gz"),
         source=sha(RAW/"files.json"),protocol=sha(D/"PROTOCOL_RU.md"),tokenization=sha(D/"mechanism.py"),
         program=sha(D/"project_actions.py")))
    print("Sealed literal line equality classes for",len(seen),"actions.")


if __name__=="__main__":main()

