"""Conditional exact random-ranking diagnostics on the fixed edit2ripple expansion gate."""
from collections import Counter
from fractions import Fraction
import gzip
import json
from extract import HERE,save

def reference(tasks):
    # Each task has either zero or one rewarded fifth read. Enumerate score mass
    # in exact fractions; infer only relative to this specified random policy.
    dist={Fraction(0):Fraction(1)}
    for n,good,gold_size in tasks:
        p=Fraction(good,n)
        nxt=Counter()
        for s,mass in dist.items():
            nxt[s]+=(1-p)*mass
            nxt[s+Fraction(1,gold_size)]+=p*mass
        dist={s:v for s,v in nxt.items() if v}
    assert sum(dist.values())==1
    return dist

def main():
    runs=json.load(gzip.open(HERE/"expanded-ranks.json.gz"))
    grades=json.load(gzip.open(HERE/"expanded-graded.json.gz"))
    panels={"gated_pool":[],"any_witness_on_same_tasks":[]}
    notes={}
    observed=Fraction(0)
    active=0
    for q,r in runs.items():
        ranked=r["ranked"]["corroborated"]
        if ranked==r["ranked"]["lexical"]:
            continue
        active+=1
        gold=grades[q]["gold"]
        all_witness=[p for p,count,agree,*_ in r["evidence"]]
        eligible=[p for p,count,agree,*_ in r["evidence"] if count>=2 or agree]
        assert ranked[4] in eligible and min(map(len,[all_witness,eligible]))>0
        observed+=Fraction(int(ranked[4] in gold),len(gold))
        notes[q]={"eligible":len(eligible),"qualified_gold":len(set(eligible)&set(gold)),
                  "held_out_gold":len(gold),"chosen_is_gold":ranked[4] in gold,
                  "replaced_is_gold":r["ranked"]["lexical"][4] in gold}
        for label,pool in zip(panels,(eligible,all_witness)):
            panels[label].append([len(pool),len(set(pool)&set(gold)),len(gold)])
    comparisons={}
    for label,tasks in panels.items():
        dist=reference(tasks)
        expect=sum(s*p for s,p in dist.items())
        comparisons[label]={"expected_recall_points_on_54":float(100*expect/len(runs)),
            "observed_minus_random_pp":float((observed-expect)*100/len(runs)),
            "probability_match_or_exceed_observed":float(sum(p for s,p in dist.items() if s>=observed)),
            "expected_gold_files":sum(g/n for n,g,_ in tasks),
            "only_one_candidate":sum(n==1 for n,_,_ in tasks),"total_eligible_candidates":sum(n for n,_,_ in tasks)}
    out=dict(active=active,details=notes,observed_new_fifth_slot_gold=sum(r["chosen_is_gold"] for r in notes.values()),
             replaced_fifth_slot_gold=sum(r["replaced_is_gold"] for r in notes.values()),reference=comparisons)
    save(HERE/"conditional-control.json",out)
    print(active,comparisons)
if __name__=="__main__":
    main()
