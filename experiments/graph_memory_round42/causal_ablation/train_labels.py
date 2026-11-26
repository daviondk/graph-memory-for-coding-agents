"""Independent train-only matching of the original evidence quotes and visible candidate intervals."""
from collections import Counter,defaultdict
import hashlib,sys
from core42 import D,OFF,R41,read,save,sha
sys.path.insert(0,str(R41))
import native
from graph_memory.datasets.isetrace import benchmark_adapter as notes
from graph_memory.trajectories import SourceSpan,source_spans_overlap


def main():
    api=native.api;sdk=api.pilot
    split=read(OFF/"split.json.gz")["train"]
    qs=defaultdict(list)
    for r in split:qs[r["t"]].append(r["q"])
    needed={r["q"] for r in split}
    examples={r["id"]:notes._QUERY_ADAPTER.validate_python(r) for _,r in sdk.stream(sdk.Q) if r["id"] in needed}
    assert set(examples)==needed
    records={}
    for sh in range(8):
        src=api.RAW/f"trajectories-{sh:05d}.jsonl"
        assert sha(src)==read(R41/f"forecast-{sh}-seal.json")["source"]
        for raw,item in sdk.stream(src):
            t=item["session_id"]
            if t not in qs:continue
            tr=native.adapt_isetrace_record(native.parse_isetrace_record(item),source_revision=sdk.RAW[1])
            cut,_=native.midstep(tr)
            visible={e.event_id for e in tr.events[:cut+1]}
            proj=read(api.TRAINED/"projection/train"/(t+".json.gz"))
            assert proj["digest"]==hashlib.sha256(raw).hexdigest()
            source={k["item_id"]:tuple(SourceSpan.model_validate(v) for v in k["source_spans"]) for k in proj["pool"]}
            published={r["q"]:set(r["positive"]) for r in proj["qs"]}
            ids=sorted(k for k,v in source.items() if all(s.event_id in visible for s in v))
            for q in qs[t]:
                m=notes._match_task_text(examples[q],tr)
                assert m is not None
                gold=notes._resolve_gold_spans(examples[q],m)
                target={k for k,spans in source.items() if any(source_spans_overlap(v,g) for v in spans for g in gold)}
                assert target==published[q]
                label=bytes(int(k in target) for k in ids)
                records[q]=[t,len(ids),sum(label),hashlib.sha256(label).hexdigest()]
        print("train quote audit",sh,len(records),flush=True)
    assert len(records)==3894
    p=D/"train-labels.json.gz";save(p,records)
    save(D/"train-label-seal.json",dict(labels=sha(p),queries=len(records),query_file=sha(sdk.Q),split=sha(OFF/"split.json.gz"),
        original_matcher=sha(__import__("pathlib").Path(notes.__file__)),code=sha(D/"train_labels.py")))


if __name__=="__main__":main()
