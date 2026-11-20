"""Repair the root experiment's filenames after two independent experiments used the same prefix.
The underlying measurements in incremental_items.json.gz and cycle_items.json.gz remained intact.
Use only the recorded self-authored functions.exec request for this experiment. No user text is read into artifacts.
"""
import gzip,json,hashlib,statistics
from pathlib import Path
from collections import defaultdict
import numpy as np
D=Path(__file__).resolve().parent
def main():
    import sys
    log=Path(sys.argv[1])  # Optional local self-authored call log; not needed to reproduce the benchmark.
    key='text(await wr("repo/incremental.py",'+chr(96)+'"""Maintain the round-4'
    code=None
    with log.open(encoding="utf8") as f:
        for line in f:
            if "Maintain the round-4 candidate graph as files arrive" not in line:continue
            p=json.loads(line).get("payload",{})
            raw=p.get("input","") or p.get("arguments","")
            if isinstance(raw,str) and key in raw:
                start=raw.index(key)+len(key.split(chr(96))[0])+1
                end=raw.index(chr(96)+"))",start)
                code=raw[start:end];break
    assert code and code.startswith('"""Maintain') and code.endswith('main()\n')
    hashof=lambda data:hashlib.sha256(data).hexdigest()
    required=json.loads((D/"cycle_lock.json").read_bytes())["incremental_lock.json"]
    for nl,endline in (("\n","\r\n"),("\n","\n"),("\r\n","\r\n"),("\r\n","\n"),("\n","")):
        raw=code.replace("\n",nl).encode()+endline.encode()
        hashes={p.name:hashof(p.read_bytes()) for p in [D.parent/"encoder"/"blind.jsonl.gz",D/"incremental.py",D/"memory.py",D/"INCREMENTAL_RU.md"]}
        hashes["incremental.py"]=hashof(raw)
        lock=json.dumps(hashes).encode()
        if hashof(lock)==required:break
    else:raise ValueError("Source recovery did not match its pre-existing independent lock.")
    (D/"incremental.py").write_bytes(raw);(D/"incremental_lock.json").write_bytes(lock)
    items=json.loads(gzip.decompress((D/"incremental_items.json.gz").read_bytes()));results={}
    for label in ("listed","shuffled"):
        selected=[i for i in items if i["order"]==label];groups=defaultdict(list)
        for x in selected:groups[x["project"]].append(x)
        methods=("each","add_each","final","add_final");x=np.array([[sum(i["times_ns"][m] for i in g) for m in methods] for g in groups.values()])
        b=x[np.random.default_rng(7711).integers(len(x),size=(10000,len(x)))].sum(axis=1);total=x.sum(axis=0)
        results[label]={"n":len(selected),"projects":len(groups),"checkpoints":sum(q["checks"] for q in selected),"times_cpu_s":{k:float(v/1e9) for k,v in zip(methods,total)},"repeat_speedup":float(total[0]/total[1]),"repeat_speedup_ci":np.quantile(b[:,0]/b[:,1],[.025,.975]).tolist(),"single_ratio_new_to_base":float(total[3]/total[2]),"postings_per_task_median":statistics.median(z["postings"] for z in selected)}
    (D/"incremental_results.json").write_text(json.dumps(results,indent=2),encoding="utf8")
    (D/"root_recovery.json").write_text(json.dumps({"original_code_digest":hashes["incremental.py"],"original_lock_digest":required,"matches_prior_cycle_lock":True,"statistics_recomputed_from_original_observations":True}),encoding="utf8")
    print("matched",required)
if __name__=="__main__":main()



