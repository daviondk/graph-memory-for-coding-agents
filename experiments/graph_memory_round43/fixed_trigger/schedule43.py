"""Independent raw streaming boundary and adversarial end-of-prefix test."""
from collections import Counter
import json
from pathlib import Path
from trigger43 import cut
from io43 import D,OFF,R41,read,sha,save


def forbidden_suffix(prefix):
    yield from prefix
    raise AssertionError("the trigger consumed a future message")


def independent(messages):
    balance=0;closures=0;calls=0
    for j,m in enumerate(messages):
        n=len(m.get("tool_calls",())) if m["role"]=="assistant" else 0
        balance+=n;calls+=n
        if m["role"]=="tool":
            balance-=1
            assert balance>=0
            if balance==0:
                closures+=1
                if closures==8:return j+1,closures,calls
    assert balance==0
    return None,closures,calls


def main():
    reg=read(D/"registration.json")
    assert reg["gate"]==sha(D/"trigger43.py")
    valid={r["t"] for r in read(OFF/"split.json.gz")["test"]}
    measures=Counter();found={}
    for sh in range(8):
        p=Path("D:/CodexResearch/x20-isetrace-runtime/inputs/trajectories")/f"trajectories-{sh:05d}.jsonl"
        assert sha(p)==read(R41/f"forecast-{sh}-seal.json")["source"]
        with p.open(encoding="utf8") as src:
            for line in src:
                raw=json.loads(line)
                t=raw["session_id"]
                if t not in valid:continue
                n,k,c=independent(iter(raw["messages"]))
                delivery=cut(iter(raw["messages"]) if n is None else forbidden_suffix(raw["messages"][:n]))
                prefix,kk,cc=delivery
                assert k==kk and c==cc and (None if prefix is None else len(prefix))==n
                if n is not None:
                    assert prefix[-1]["role"]=="tool"
                    measures["poisoned_suffixes_unread"]+=1
                found[t]=[n,k,c];measures["histories"]+=1
    assert set(found)==valid and measures["histories"]==1207
    p=D/"schedule-audit.json.gz";save(p,found)
    save(D/"schedule-audit-seal.json",dict(counts=measures,data=sha(p),code=sha(D/"schedule43.py"),registered=sha(D/"registration.json")))
    print(measures)


if __name__=="__main__":main()
