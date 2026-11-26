"""Independent reconstruction from prefixes and closed-form actual SQLite write counts."""
from pathlib import Path
import json,gzip,hashlib,math
from collections import Counter
from statistics import mean

D=Path(__file__).resolve().parent
def read(name):
    p=D/name;data=p.read_bytes();return json.loads(gzip.decompress(data) if p.suffix==".gz" else data)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def rank(p,n):return hashlib.sha256(("R37-128|"+p+"|"+str(n)).encode()).digest()
def main():
    plan=read("plan.json");seal=read("run-seal.json")
    assert plan["parent"]==sha(D.parent/"code_visibility"/"manifest.json")
    for k,p in (("storage.py","sqlite_code"),("benchmark.py","benchmark_code"),("PROTOCOL_RU.md","protocol"),("inputs.py","prepare_code"),("prefix_inputs.json.gz","input"),("reference.json.gz","evaluator")):
        assert sha(D/k)==plan[p]
    assert sha(D/"full_counts.json.gz")==seal["full"] and sha(D/"timings.json.gz")==seal["timed"]
    inputs=read("prefix_inputs.json.gz");gold=read("reference.json.gz");counts=read("full_counts.json.gz");timings=read("timings.json.gz");res=read("results.json")
    parent={q["q"]:q["mem"]["T"] for q in json.loads(gzip.decompress((D.parent/"code_visibility"/"predictions.json.gz").read_bytes()))}
    assert gold==parent and set(gold)==set(inputs)==set(counts)
    assert plan["panel"]==sorted(inputs,key=lambda k: hashlib.sha256(("R37-code-store|"+k).encode()).digest())[:128]
    cumulative={m:Counter() for m in "AML"}
    for q,x in inputs.items():
        prior=dict(x["base"]);receipt=dict(x["receipt"]);ans=receipt.copy()
        if x["start"] is not None:
            candidates=[]
            for n,s in prior.items():
                if x["start"]<=n<=x["end"]:continue
                j=n+x["delta"] if n>x["end"] else n
                if j not in receipt:candidates.append((j,s))
            for j,s in sorted(candidates,key=lambda t:rank(x["path"],t[0]))[:128-len(ans)]:ans[j]=s
        assert sorted(ans.items())==[tuple(t) for t in gold[q]]
        fixed=set(ans.items())&set(prior.items())
        m_cost=max(len(ans),len(prior))-len(fixed)
        a_cost=len(set(prior)^set(ans))+sum(prior[n]!=ans[n] for n in set(prior)&set(ans))
        expected={"A":a_cost,"M":m_cost,"L":1+len(receipt)}
        assert m_cost<=a_cost
        for m,cost in expected.items():
            rec=counts[q][m]
            assert rec["writes"]==cost and rec["rows_out"]==len(ans)
            assert rec["pre_read_rows"]==(0 if m=="L" else len(prior))
            assert rec["read_rows"]==(1+len(receipt)+(len(prior) if x["start"] is not None else 0) if m=="L" else len(ans))
            cumulative[m].update(rec)
    for m,v in cumulative.items():
        pp=seal["page_metrics"][m];assert v==res["totals"][m] and v["wal_bytes"]==32+v["wal_frames"]*(24+pp["final"]["page_size"])
        assert pp["final"]["wal"]==v["wal_bytes"]
    for m in "AML":
        val=mean(mean(rep[m][0]+rep[m][1] for rep in z) for z in timings.values())
        assert math.isclose(val,res["times"]["wall_ns"]["update_first"][m]["mean"])
    print(f"Checked independent transition reconstruction and row counts for {len(inputs)} episodes × 3; WAL frames and timing totals for {len(timings)} blocks.")
if __name__=="__main__":main()
