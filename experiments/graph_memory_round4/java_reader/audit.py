"""Verify literal target and output counts, index alignment and request lineage independently."""
import gzip, json, sys
from pathlib import Path
from collections import Counter
from infer import D, read, save, sha, from_str
sys.path.insert(0,str(D.parent/"repo"))
from data_io import rows, files
def main():
    ids=set();totals={};refs={}
    for path in files("java","test"):
        refs[path.name]=[(r["next_line"].strip(),r["gold_snippet_index"]) for r in rows(path,["next_line","gold_snippet_index"])]
    for key in ("A","B","Z"):
        inputrows={r["id"]:r for r in read(key+"_packets.json.gz")};a=read(key+"_assignment.json"); calls={};usage=Counter()
        locks=read(key+"_decisions.json")
        assert set(a)==set(inputrows)
        for n,h in locks.items():
            p=D/(key+"_calls")/n;x=read(p);r=x["reply"];k=sha(from_str(x["request"]))
            assert sha(p.read_bytes())==h and n==k+".json.gz" and r["id"] not in ids
            ids.add(r["id"]);calls[k]=r;usage.update({f:r["usage"][f] for f in ("prompt_tokens","completion_tokens")})
        assert {k for v in a.values() for k in v.values()}==calls.keys()
        counts=Counter()
        if key!="Z":
            scored=read(key+"_selective_items.json.gz"); q=read(key+"_results.json")["all"]; eq=read("selective_results.json")[key]["methods"]
            for s in scored:
                i=s["id"];r=inputrows[i];gold,decl=refs[r["file"]][r["local_index"]];assert s["gold"]==gold
                for arm,m in s["methods"].items():
                    assert m["em"]==int(gold==m["generated"]);counts[arm]+=m["em"]
                    if arm in ("graph","semlith"):
                        assert m["retrieved"]==int(r["ranks"][arm]==decl)
                for arm,k in a[i].items():
                    assert calls[k]["usage"]["prompt_tokens"]==s["methods"][arm]["prompt_tokens"]
            assert {k:v["em"] for k,v in eq.items()}==dict(counts)
            assert all(counts[m]==v["em"] for m,v in q["methods"].items())
        totals[key]=dict(issues=len(a),calls=len(calls),tokens=dict(usage),em=dict(counts))
    save("audit.json",{"total_independent_llm_requests":len(ids),"panels":totals})
if __name__=="__main__":main()

