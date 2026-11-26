"""Count which public state fields and inputs each compared system can use; do not open judgments."""
from common import *
CANONICAL=("information_need","current_subgoal","issue")
EXTRA=("current_hypothesis","current_observation","latest_test_output","search_queries","opened_files","current_diff")
def present(x):
    if isinstance(x,dict):return any(present(v) for v in x.values())
    if isinstance(x,(list,tuple)):return any(present(v) for v in x)
    return bool(x.strip()) if isinstance(x,str) else bool(x)
def main():
    panel=read(OUT/"panel.json");ids=set(panel["order"]);seen={}
    with gzip.open(PUB/"items.jsonl.gz","rt",encoding="utf8") as f:
        for item in map(json.loads,f):
            q=item["state_id"]
            if q not in ids:continue
            seen[q]={field:int(present(item.get(field))) for field in CANONICAL+EXTRA}
    assert set(seen)==ids
    checks={}
    for n,qs in (("all214",panel["order"]),("outside204",panel["remaining"])):
        checks[n]=dict(states=len(qs),present={key:sum(seen[q][key] for q in qs) for key in CANONICAL+EXTRA},
                 any_additional=sum(any(seen[q][key] for key in EXTRA) for q in qs),
                 all_additional=sum(all(seen[q][key] for key in EXTRA) for q in qs))
    save("input-contract.json",dict(qwen_query=CANONICAL,additional_R39=EXTRA,panels=checks,by_state=seen,
        sources=dict(gguf=sha(R39SRC/"reference.py"),R39=sha(WORK/"graph_memory_round39/repo_crossfit/public.py"),public=sha(PUB/"items.jsonl.gz"),panel=sha(OUT/"panel.json"))))
    print(checks)
if __name__=="__main__":main()
