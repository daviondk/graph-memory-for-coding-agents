"""Apply the paper's observed-overlap diagnostic to locked crossfitted SERBench forecasts."""
from panel import *
from collections import Counter
sys.path.insert(0,str(ROOT.parent/"repo_crossfit"))
from grade import summarize
from data import labels


def main():
    path=ROOT.parent/"repo_crossfit/outcomes.json.gz"
    rows=read(path)
    states=set(rows)
    gold=labels(states)
    observed={}
    stage={}
    count=Counter()
    with gzip.open(PUB/"items.jsonl.gz","rt",encoding="utf8") as f:
        for r in map(json.loads,f):
            q=r["state_id"]
            if q not in states:
                continue
            visible=set(r["observed_evidence_ids"])
            observed_in_pool={c["evidence_id"] for c in r["candidate_evidence"] if c["observed_by_state"]}
            available={c["evidence_id"] for c in r["candidate_evidence"]}
            count["pool_flag_vs_list_mismatch_states"]+=int(observed_in_pool!=available&visible)
            count["pool_flag_vs_list_mismatch_entries"]+=len(observed_in_pool^(available&visible))
            count["nonempty_state_lists"]+=int(bool(visible))
            count["nonempty_label_lists"]+=int(bool(gold[q]["observed_evidence_ids"]))
            allowed={x for g in gold[q]["required_evidence_groups"] for x in g["acceptable_evidence_ids"]}
            allowed.update(x for route in gold[q]["alternative_minimal_sets"] for x in route)
            assert allowed.isdisjoint(visible) and allowed.isdisjoint(observed_in_pool)
            count["observed_fragments"]+=len(observed_in_pool)
            observed[q]=bool(observed_in_pool)
            stage[q]=r["state_type"]
    assert observed.keys()==rows.keys()
    hidden=Counter()
    with gzip.open(PUB.parent/"test500/items.jsonl.gz","rt",encoding="utf8") as f:
        for r in map(json.loads,f):
            ids=set(r["observed_evidence_ids"])
            pool={c["evidence_id"] for c in r["candidate_evidence"]}
            flagged={c["evidence_id"] for c in r["candidate_evidence"] if c["observed_by_state"]}
            hidden["states"]+=1
            hidden["states_with_overlap"]+=int(bool(flagged))
            hidden["flags"]+=len(flagged)
            hidden["mismatch"]+=int(flagged!=ids&pool)
    summaries={}
    for flag in (False,True):
        qs={q for q,f in observed.items() if f==flag}
        summary=summarize({q:rows[q] for q in qs},"proposed")
        summary["stages"]=dict(Counter(stage[q] for q in qs))
        summaries["overlap" if flag else "no_overlap"]=summary
    write("strata-results.json",dict(scores=summaries,pool_counts=dict(count),blind_input_only=dict(hidden),native_file=sha(path),
                                    protocol=sha(ROOT/"STRATA_PROTOCOL_RU.md"),code=sha(Path(__file__))))
    for key,r in summaries.items():
        print(key,r["states"],r["repos"],r["successes"])


if __name__=="__main__":
    main()
