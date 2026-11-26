from panel import *
import sys
from collections import Counter
def main():
    plan=load(D/"plan.json");r=load(D/"results.json");seal=load(D/"run-seal.json");run=load(D/"run-plan.json");excluded=load(D/"excluded.json")
    assert plan["panel_code"]==sha(D/"panel.py") and plan["protocol"]==sha(D/"PROTOCOL_RU.md") and run["program"]==sha(D/"measure.py") and run["panel"]==sha(D/"plan.json") and r["code"]==sha(D/"analysis.py") and r["source_seal"]==sha(D/"run-seal.json") and seal["plan"]==sha(D/"run-plan.json")
    assert sha(P/"manifest.json")==plan["r36"] and sha(SW/"manifest.json")==plan["streaming"]
    hist={}
    for f,x in seal["parts"].items():assert sha(D/f)==x;hist.update(load(D/f))
    assert {t for t,v in hist.items() if v["status"]!="retained"}==set(excluded)
    assert set(hist)==set(plan["panel"]) and sum(r["selection"]["statuses"].values())==512 and Counter(v["status"] for v in hist.values())==r["selection"]["statuses"]
    for cut in ["25","50","75","100"]:
        for typ in ["pu","groups"]:
            rows=[z["cuts"][cut][typ] for z in hist.values() if z["status"]=="retained"];s=r["panels"][cut+"_"+typ]["unannotated"];assert all(E<=M<=L and M-E==oo and L-M==nn for E,M,L,oo,nn in rows)
            assert list(map(sum,zip(*rows)))==s["sum_E_M_L_once_never"]
            assert sum(q[4]>0 for q in rows)==s["with_never"] and sum(q[3]+q[4]==0 for q in rows)==s["no_extra"]
    nc=sum(len(z["native_states"]) for z in hist.values() if z["status"]=="retained");assert nc==r["reconstruction"]["native_prefixes"] and 2*nc==r["native_pairset_hash_checks"]
    out=D/"manifest.json"
    if "--seal" in sys.argv:save(out,{"algorithm":"SHA-256","files":{p.name:sha(p) for p in sorted(D.iterdir()) if p.is_file() and p!=out}})
    files=load(out)["files"];assert {p.name for p in D.iterdir() if p.is_file() and p!=out}==set(files);assert all(sha(D/p)==h for p,h in files.items());print(len(files),"files",sha(out))
if __name__=="__main__":main()
