"""Post hoc check of the matching mechanism on single-event, one-call and cross-call evidence."""
import collections
import json
import re
from pathlib import Path
from summarize import load,matched,summary
ROOT=Path(__file__).resolve().parent
def fit(path):
    labels=load(path/"gold-spans.json.gz")
    groups={}
    for q,target in labels.items():
        kind=set();calls=set();events=set()
        for span in target:
            m=re.fullmatch(r"(.+?):(call|output):(.+)",span["event_id"])
            assert m
            kind.add(m[2]);calls.add((m[1],m[3]));events.add(span["event_id"])
        if len(events)==1:label="one_event"
        elif len(calls)==1:label="two_events_one_call"
        else:label="multiple_calls"
        groups[q]=label
    rows=[r for r in load(path/"outcomes.json.gz") if r["budget"]==2048 and r["view"]=="provenance"]
    results={}
    for group in sorted(set(groups.values())):
        arms=collections.defaultdict(dict)
        for r in rows:
            if groups[r["query"]]==group:arms[r["policy"]][r["query"]]=r
        results[group]={"arms":{p:summary(list(rs.values())) for p,rs in arms.items()},"related_minus_skip":matched(arms["related"],arms["skip"]),"related_minus_value":matched(arms["related"],arms["value"])}
    return results
if __name__=="__main__":
    d={k:fit(p) for k,p in (("first",ROOT),("repeat",ROOT/"replication"))}
    (ROOT/"posthoc-events.json").write_text(json.dumps(d,indent=2)+"\n",encoding="utf8")
    for k,stats in d.items():
        for group,g in stats.items():
            print(k,group,g["arms"]["prefix"]["n"],[(a,r["full"]) for a,r in g["arms"].items()])
