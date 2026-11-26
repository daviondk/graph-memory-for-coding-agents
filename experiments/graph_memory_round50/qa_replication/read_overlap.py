from collections import Counter
from paths_repl import *

def main():
    view=get(P/"visible.json.gz");orders=get(D/"orders.json.gz");history=get(P/"seen-documents.json.gz")
    prior={k:set(v) for k,v in history.items()}
    counts={};pool=set.union(*prior.values());details={}
    for q,r in orders.items():
        docs={i:hexb((t+"\0"+b).encode()) for i,t,b in view[q][1]}
        targets={"true":r["true"],"lex":r["lex"],"sham47011":r["sham"]["47011"]["second"]}
        assert docs[r["seed"]] not in pool
        details[q]={key:[docs[j],sorted(k for k,v in prior.items() if docs[j] in v)] for key,j in targets.items()}
    for arm in ("true","lex","sham47011"):
        counts[arm]=sum(bool(v[arm][1]) for v in details.values())
    put(D/"read-overlap.json.gz",details)
    put(D/"read-overlap-summary.json",dict(historical_second=counts,all_new_inputs=sum(not any(vv[1] for vv in v.values()) for v in details.values()),
        n=len(view),details=sha(D/"read-overlap.json.gz")))
if __name__=="__main__":main()
