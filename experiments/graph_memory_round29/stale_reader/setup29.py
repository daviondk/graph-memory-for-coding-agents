"""Sealed benchmark assembly: isolate dates and types from the retrieval and response models."""
import gzip,hashlib,json,os
from pathlib import Path
D=Path(__file__).resolve().parent;P=Path("D:/CodexResearch/x20-r29-stale-reader");W=D.parents[1];R28=W/"graph_memory_round28/retraction_sources"
DATA=Path("D:/CodexResearch/x20-r28-retraction/stale-projection")
def h(x):return hashlib.sha256(x.encode() if isinstance(x,str) else x).hexdigest()
def sha(p):return h(p.read_bytes())
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def save(p,obj):
    b=(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
    t=p.with_name(p.name+".tmp");t.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
    import time
    for i in range(7):
        try:os.replace(t,p);return
        except PermissionError:time.sleep(.025*(2**i))
    os.replace(t,p)
def main():
    from collections import defaultdict,Counter
    seal=read(R28/"blind-seal.json");lp=DATA/"evaluator/labels.json.gz";qp=DATA/"questions.json"
    assert sha(lp)==seal["labels_sha"] and sha(qp)==seal["questions_sha"]
    labels=read(lp);allqs={r["qid"]:r["question"] for r in read(qp)};by=defaultdict(dict);types=defaultdict(set)
    for r in labels:
        by[r["case"]][r["dimension"]]=r;types[r["scenario_type"]].add(r["case"])
    sortkey=lambda c:h("r29-stale-reader-v1/"+c)
    selected=[(typ,c) for typ,cs in sorted(types.items()) for c in sorted(cs,key=sortkey)[:4]];assert len(selected)==8
    tasks={};secrets={};histories={};oracle={};public=[]
    for typ,c in selected:
        path=DATA/"history"/(c+".json.gz");assert sha(path)==seal["history"][c]
        hist=read(path)["sources"];histories[c]=hist;src={v["id"]:v for v in hist}
        rr=by[c];r=rr["dim1_query"];a,b=src[r["old_source"]],src[r["new_source"]]
        assert a["sequence"]<b["sequence"];at=(a["sequence"]+b["sequence"])//2;ts=hist[at]["time"]
        public.append([typ,c])
        for mode in ("dim1_query","dim2_query","dim3_query","past_prefix","past_full"):
            base=rr.get(mode,r);subject=allqs[base["qid"]];q=h("r29-case-question/"+c+mode)[:24];past=mode.startswith("past")
            ask=(f"Using only records through {ts}, what was the last situation or intention the user explicitly reported on the topic below? Describe the report at its own time. A temporary state need not have persisted until the cutoff. Topic: {subject}" if past else subject)
            tasks[q]=dict(case=c,query=subject,ask=ask,available_until=at if mode=="past_prefix" else len(hist)-1,
                          asof=at if past else None)
            secrets[q]=dict(case=c,mode=mode,type=typ,old=r["old"],new=r["new"],rubric=r["rubric"],
                            old_source=a["id"],new_source=b["id"],original_qid=base["qid"],date=ts)
            oracle[q]=[[a["time"],r["old"]]]+([] if mode=="past_prefix" else [[b["time"],r["new"]]])
    assert len(tasks)==40 and set(tasks)==set(secrets)==set(oracle)
    save(D/"cohort.json",public);save(P/"reader-questions.json",tasks);save(P/"reader-histories.json.gz",histories)
    save(P/"eval-keys.json.gz",secrets);save(P/"oracle.json.gz",oracle)
    save(D/"input-seal.json",dict(plan=sha(D/"PROTOCOL_RU.md"),source=sha(R28/"blind-seal.json"),cohort=sha(D/"cohort.json"),
         questions=sha(P/"reader-questions.json"),histories=sha(P/"reader-histories.json.gz"),eval_keys=sha(P/"eval-keys.json.gz"),
         oracle=sha(P/"oracle.json.gz"),code=sha(Path(__file__)),n=len(tasks),types=dict(Counter(t for t,c in selected))))
if __name__=="__main__":main()
