"""After freezing predictions, check all admitted historical observations in their own revision."""
from rec_data import *
import time
import pyarrow.parquet as pq
def main():
    assert read(HERE/"forecast-seal.json")["forecasts"]==sha(HERE/"forecasts.json.gz")
    targets=signed_input=read(HERE/"receipt-inputs.json.gz");cache={};examined=set();stats=Counter()
    for part in read(RAW/"files.json")["events"]:
        f=RAW/part["file"];assert sha(f)==part["sha"]
        for batch in pq.ParquetFile(f).iter_batches(columns=["run_id","event_index","event_json"],batch_size=384):
            for k,(run,at) in enumerate(zip(batch.column(0).to_pylist(),batch.column(1).to_pylist())):
                if run not in cache:cache[run]=h(run)
                rid=cache[run]
                if rid not in targets or str(at) not in targets[rid]:continue
                rows=targets[rid][str(at)];s=json.loads(batch.column(2)[k].as_py())["raw"]["observation"].get("new_content")
                examined.add((rid,at));stats["receipts"]+=1;stats["rows"]+=len(rows)
                if not isinstance(s,str):
                    stats["missing_snapshot"]+=1;stats["unknown_rows"]+=len(rows);continue
                lines=s.split("\n")
                for n,d,size,_ in rows:
                    ok=1<=n<=len(lines) and h(lines[n-1])==d and len(lines[n-1].encode())==size
                    stats["exact" if ok else "wrong"]+=1
    assert sum(len(t) for t in targets.values())==len(examined)
    store_file("historical-audit.json",dict(stats=stats,program=sha(HERE/"audit_receipts.py"),seals=sha(HERE/"forecast-seal.json")))
    print("Audited",dict(stats))
if __name__=="__main__":main()
