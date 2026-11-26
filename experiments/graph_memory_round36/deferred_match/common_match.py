import hashlib,json,gzip,os,sys,importlib.util
from pathlib import Path
from collections import Counter
for name in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[name]="1"
D=Path(__file__).resolve().parent;W=D.parents[1];P=D.parent/"streaming_witnesses";R=D.parent/"materialized_append";sys.path.insert(0,str(R))
import materialize as old
from graph_memory.graphs.provenance.builder import _argument_contains,_typed_tokens
from operator_match import DeferredFeeds
from materialize import l,load,put,sha,np
spec=importlib.util.spec_from_file_location("matched_prior_operator",P/"reader.py");eager=importlib.util.module_from_spec(spec);spec.loader.exec_module(eager)
SOURCE="08a84ae9dac2ea21cea036cbce59661992905e51cd3a37b0b58bc16d97756bb9"
def args_wire(e):
    return e.raw_arguments,json.dumps(e.arguments,ensure_ascii=False,separators=(",",":"))
def rows(sh,subset=None):
    ix=l.ref.graph_index();base=load(R/f"graphs-{sh}.json.gz");want=set(base) if subset is None else set(base)&set(subset)
    if not want:return
    raw=l.env.RAW/f"trajectories-{sh:05d}.jsonl";assert sha(raw)==load(old.R34/"plan.json")["raw"][raw.name]
    for buf,obj in l.env.pilot.stream(raw):
        t=obj["session_id"]
        if t not in want:continue
        fp,sig=ix[t];assert sha(fp)==sig;record=load(fp);assert hashlib.sha256(buf).hexdigest()==record["raw_source"]
        chunks=Counter(n["attributes"]["call_id"] for n in record["g"]["nodes"] if n["kind"]==l.ref.OUTPUT_CHUNK_NODE)
        tr=l.parent.adapt_isetrace_record(l.parent.parse_isetrace_record(obj),source_revision=l.env.pilot.RAW[1])
        yield t,tr.events,chunks,base[t]
def seal_plan():
    assert sha(P/"manifest.json")==SOURCE
    targets={r["t"] for r in load(l.ref.TR/"split.json.gz")["test"]};panel=sorted(targets,key=lambda t:hashlib.sha256(("R36-deferred-match-cpu|"+t).encode()).digest())[:96]
    put(D/"plan.json",dict(protocol=sha(D/"PROTOCOL_RU.md"),baseline_manifest=SOURCE,operator=sha(D/"operator_match.py"),baseline_code=sha(P/"reader.py"),timed_ids=panel,
        timestamp_definition="(message_index,sub_index)",native_predicate=sha(Path(sys.modules[_argument_contains.__module__].__file__))))
if __name__=="__main__":seal_plan()