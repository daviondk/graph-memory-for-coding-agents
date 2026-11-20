"""Before external scoring, verify the three copied policy branches against the previous locked bytes."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,itertools,json,sys
D=Path(__file__).resolve().parent;O=D.parent/"real_swe"
import writer_followup as w
locked=json.loads((O/"checkpoint_lock.json").read_bytes())
weights=w.read(w.R2/"edit_memory/model.json")["flat"],w.read(w.R2/"span_memory/width_model.json"),w.read(w.R2/"span_memory/offset.json")["intercept"]
counts=Counter()
for shard in range(8):
    fn=f"events_{shard}.jsonl.gz";assert hashlib.sha256((O/fn).read_bytes()).hexdigest()==locked[fn]
    task=next(w.rows(O/f"source_{shard}.jsonl.gz"));stream=iter(w.rows(O/fn))
    obs=task["events"];blobs={a:w.empty(a) for a in ("lru","point","typed")}
    for t,e in enumerate(obs,1):
        i,n,rec=next(stream);assert n==t and i==task["instance"]
        for arm,b,want,sz,before,evicted,npack in rec:
            blob,meta=w.transition(blobs[arm],e,task,weights,4096);blobs[arm]=blob
            assert w.h(blob)==want and meta==(before,sz,evicted,npack)
            counts[arm]+=1
info={"exact_checkpoint_and_diagnostics_on_first_prior_issue_each_shard":dict(counts),"reference_issues":8}
(D/"control_audit.json").write_text(json.dumps(info,indent=1));print(info)

