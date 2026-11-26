"""Exhaust finite timelines for temporal projection and the single-read specialization."""
import itertools
import json
from pathlib import Path

def check():
    horizon=7
    total=phantoms=single=invalid_shortcut=0
    boundary=0
    for bits in itertools.product((False,True),repeat=horizon):
        for first,second in itertools.product(range(horizon+1),repeat=2):
            visible=max(first,second)
            for last in range(horizon):
                logical=any(bits[:last+1]) and visible<=last
                history=any(bits[t] and first<=t and second<=t for t in range(last+1))
                overlap=visible<=last and any(bits[visible:last+1])
                assert overlap==history
                assert not history or logical
                total+=1;phantoms+=logical and not history
                # All witnesses for one consumer are created at its call. There is at
                # most one active interval afterwards. A source output precedes the call.
                for call in range(first+1,second+1):
                    if any(bits[:call]) or any(bits[k] and not bits[k-1] for k in range(call+1,horizon)):
                        continue
                    once=visible<=last and bits[second]
                    assert once==history
                    single+=1
                    if second<horizon and second>call and bits[second-1] and not bits[second]:
                        boundary+=1
                if visible<=last and history!=bits[visible]:
                    invalid_shortcut+=1
    assert phantoms and invalid_shortcut and boundary
    return dict(horizon=horizon,snapshot_cases=total,late_projection_false_positives=phantoms,
                one_check_cases=single,exact_boundary_cases=boundary,
                unconstrained_single_read_counterexamples=invalid_shortcut)
if __name__=="__main__":
    p=Path(__file__).with_name("enumeration.json")
    result=check()
    p.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(result)

