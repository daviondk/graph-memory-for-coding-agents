import os,sys,time
from pathlib import Path
D=Path(__file__).resolve().parent;W=D.parents[1];R29=W/"graph_memory_round29/stale_reader"
sys.path.insert(0,str(R29))
from setup29 import read,sha,save,h,DATA
P=Path("D:/CodexResearch/x20-r31-stale-turns")
P.mkdir(exist_ok=True);(P/"shards").mkdir(exist_ok=True)
def refs():
    return read(W/"graph_memory_round28/retraction_sources/blind-seal.json")
def data():
    lock=refs();file=DATA/"questions.json";assert sha(file)==lock["questions_sha"]
    cases={}
    for q in read(file):cases.setdefault(q["case"],{})[q["qid"]]=q["question"]
    return cases
def request_id(q,ids):return h("r31-pair/"+q+"/"+"/".join(sorted(ids)))[:32]
def prep():
    sig=refs();cases=data();lf=DATA/"evaluator/labels.json.gz";assert sha(lf)==sig["labels_sha"]
    labels=read(lf);prior={r[1] for r in read(R29/"cohort.json")};sorted_new=sorted(set(cases)-prior,key=lambda c:h("r31-stale-split"+c))
    dev=prior|set(sorted_new[:72]);split={c:("dev" if c in dev else "test") for c in cases}
    priv={r["qid"]:sorted((r["old_source"],r["new_source"])) for r in labels}
    assert len(dev)==80 and len(split)==400 and len(priv)==1200 and all(len(v)==3 for v in cases.values())
    save(D/"case-split.json",split);save(P/"privileged-addresses.json.gz",priv)
    save(D/"input-seal.json",dict(source=sha(W/"graph_memory_round28/retraction_sources/blind-seal.json"),split=sha(D/"case-split.json"),
         protocol=sha(D/"PROTOCOL_RU.md"),prior=sha(R29/"cohort.json"),privileged_channel=sha(P/"privileged-addresses.json.gz"),
         code=sha(Path(__file__)),models=read(R29/"retrieval-seal.json")["e5"],qwen_tokenizer=read(R29/"retrieval-seal.json")["qwen_tokenizer"]))
if __name__=="__main__":prep()
