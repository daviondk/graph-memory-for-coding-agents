"""Audit abstention, identical source content, ties, and session roles outside the primary analysis."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
import study as s
from score import load, write

def main():
    split=load("split.json.gz")
    metrics=load("group-metrics.json.gz")["external"]
    seen_forms=collections.defaultdict(set)
    lo_norm=set()
    groups=s.ds.conv_groups(s.ds.load_locomo(str(s.LO)))
    for m in groups.values():
        by=collections.defaultdict(list)
        for t in m[0].turns:
            by[t.session_num].append(s.norm(t.text))
        lo_norm.update(s.digest(json.dumps(x,ensure_ascii=False)) for x in by.values())
    lme_norm=set()
    q_subset=collections.defaultdict(list)
    roles=collections.Counter()
    gold_origins=collections.defaultdict(set)
    for q in json.loads(s.TARGET.read_bytes()):
        k=s.digest(q["question_id"])
        is_abs=q["question_id"].endswith("_abs")
        p=metrics[k]["p"]
        q_subset["abs" if is_abs else "ordinary"].append(k)
        q_subset["all"].append(k)
        for rid, sess in zip(q["haystack_session_ids"],q["haystack_sessions"],strict=True):
            ts=tuple((z["role"],z["content"]) for z in sess)
            sh=s.sig(ts)
            seen_forms[sh].add(s.digest(json.dumps(ts,ensure_ascii=False)))
            lme_norm.add(s.digest(json.dumps([s.norm(t) for _,t in ts],ensure_ascii=False)))
            for turn in sess:
                roles[(turn["role"],turn.get("has_answer") is True)] += 1
            if any(x.get("has_answer") is True for x in sess):
                gold_origins[sh].add(k)
    more={}
    for mode, ks in q_subset.items():
        sel=[k for k in ks if metrics[k]["p"]]
        more[mode]={"total":len(ks),"positive":len(sel),"labeled_turns":sum(metrics[k]["p"] for k in ks)}
        more[mode]["R20"]={a:sum(metrics[k]["arms"][a]["metric"]["R20"] for k in sel)/len(sel) if sel else None for a in s.ARMS}
    out=dict(subgroups=more,roles={role:{"yes":roles[(role,True)],"no":roles[(role,False)]} for role in ("user","assistant")},
             normalized_sessions_with_different_raw_text=sum(len(v)>1 for v in seen_forms.values()),
             max_raw_versions_per_session=max(map(len,seen_forms.values())),cross_corpus_ignore_speaker=len(lme_norm & lo_norm),
             positive_sessions_reused_across_target_questions=sum(len(x)>1 for x in gold_origins.values()),
             max_questions_for_positive_session=max(map(len,gold_origins.values())))
    write("source-audit.json",out)
    print(out)
if __name__=="__main__":
    main()
