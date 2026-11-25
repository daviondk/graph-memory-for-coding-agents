"""Make a second projection while physically removing labels; do not access forecasts."""
from common import *
import common

original=common.source
def stripped(name):
    x=original(name)
    if name=="doc":
        for records in x["doc_data"].values():
            for key,record in records.items():
                records[key]={k:record[k] for k in ("title","doc_text")}
    else:
        for records in x["dial_data"].values():
            for d in records:
                turns=d["turns"]
                for i,turn in enumerate(turns):
                    turns[i]={k:turn[k] for k in ("role","utterance","turn_id")}
    return x
common.source=stripped
ref=common.get_views()
clean=common.packets()
assert clean==ref
# Verify every query was constructed from a strict prefix with no target or later step available.
queries={q[0]:q for q in clean["q"]}
verified=set()
for ds in stripped("dial_validation")["dial_data"].values():
    for dialog in ds:
        preceding=[]
        for turn in dialog["turns"]:
            q=short(dialog["dial_id"]+"\x1f"+str(turn["turn_id"]))
            if q in queries:
                row=queries[q]
                assert q not in verified and row[2]==" [SEP] ".join(t["utterance"] for t in reversed(preceding[-3:]))
                assert turn["role"]=="agent" and preceding[-1]["role"]=="user"
                verified.add(q)
            preceding.append(turn)
assert verified==set(queries)
print(save(ROOT/"blind-audit.json",dict(
    packets_identical_after_removing_all_gold_and_source_spans=True,queries_verified_as_strict_prefix=len(verified),
    input_lock=checksum(ROOT/"input-lock.json"),script=checksum(Path(__file__)),
    predictor_input_files=["view.json.gz","e5.npy","input-lock.json","encoder-receipt.json","fine_train/model.json","tokenizer.json"],
    note="Original target and future utterances remain in the public archive, but are absent from the query view. Repeated wording within prior messages and public text is permissible.")))
