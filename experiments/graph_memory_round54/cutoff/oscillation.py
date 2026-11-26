"""Constructed separation for a stale outside-key bound versus the current prefix cutoff."""
from collections import Counter
import json
from pathlib import Path
import sys
import tempfile
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent/"reserve"))
from classic import ClassicStore
from reserve_store import ReserveStore
from core import connect
from source import sig

def event(t,born,delta):
    return {"t":t,"born":born,"delta":delta,"sha":sig(born,delta)}
def walk(folder,cycles,plan):
    c=connect(folder/f"{cycles}-{plan}.sqlite")
    store=ClassicStore(c,8) if plan=="prefix" else ReserveStore(c,8,"lazy")
    scores={i:26-i for i in range(7)} | {7:6,8:1}
    # The common forced restart leaves each plan only the current eight and its cold bound.
    assert store.update("q",event(1,list(scores),[[i,i,v] for i,v in scores.items()]))
    store.last.clear()
    current=6;timeline=[];events=Counter()
    try:
        for i,v in enumerate([9,7]*cycles,2):
            assert store.update("q",event(i,[],[[7,7,v-current]]))
            current=scores[7]=v
            truth=sorted(scores.items(),key=lambda z:(-z[1],z[0]))[:8]
            assert store.get("q",i,8)==truth and store._history("q",i,8)==truth
            events.update(store.event)
            timeline.append(store.event["warm_probes"])
        terminal=2*cycles+2
        assert store.update("q",event(terminal,[],[[7,7,-current]]))
        assert store.get("q",terminal,8)[-1]==(8,1) and store.event["warm_probes"]==1
        return {"probes":events["warm_probes"],"rows":events["warm_rows"],"cold_probes":events["cold_probes"],
                "cold_rows":events["cold_rows"],"crossing_probe":store.event["warm_probes"],"per_update":timeline}
    finally:c.close()
def main():
    with tempfile.TemporaryDirectory() as td:
        values={str(n):{p:walk(Path(td),n,p) for p in ("prefix","bound")} for n in (1,4,32)}
    for n,r in values.items():
        assert r["prefix"]["probes"]==r["prefix"]["rows"]==int(n)
        assert r["bound"]["probes"]==r["bound"]["rows"]==0
        assert all(v["cold_rows"]==8 and v["cold_probes"]==1 for v in r.values())
    data={"purpose":"constructed counterexample, not a frequency estimate","k":8,"capacity":8,"runs":values}
    path=D/"oscillation.json"
    if "--verify" in sys.argv:assert json.loads(path.read_bytes())==data
    else:path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n",encoding="utf8")
    print([(n,r["prefix"]["probes"],r["bound"]["probes"]) for n,r in values.items()])
if __name__=="__main__":main()
