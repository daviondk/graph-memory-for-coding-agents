"""Audit the first divergence at replay using sealed messages and traces."""
import re
from collections import Counter
import experiment as x

def id_number(a):
    v=a.get("read_hit")
    if type(v) is int:return v
    if isinstance(v,str) and re.fullmatch(r"H?\d+",v):return int(v.lstrip("H"))
    return None

def main():
    ids=x.e.answers()
    summary=Counter();by_arm={"history":Counter(),"pointer":Counter()};rows=[]
    for i in ids:
        root=x.D/"tasks"/i
        lhs,rhs=(x.read(root/(m+".json.gz")) for m in ["flat","evidence"])
        assert lhs["shared"]["entry"]==rhs["shared"]["entry"]
        assert lhs["events"][0]["key"]==rhs["events"][0]["key"]
        assert lhs["events"][0]["decision"]==rhs["events"][0]["decision"]
        raw=lhs["shared"]["ptr"];first_diverge=None
        for j,(a,b) in enumerate(zip(lhs["entries"],rhs["entries"])):
            if a==b:continue
            first_diverge=j-1
            break
        if first_diverge is not None:
            a=lhs["events"][first_diverge];b=rhs["events"][first_diverge]
            assert raw and a["key"]==b["key"] and id_number(a["decision"])==id_number(b["decision"])==1
            assert a["span"] is None and (b["span"]["path"],b["span"]["center"])==(raw["path"],raw["line"])
        else:
            assert lhs["entries"]==rhs["entries"] and lhs["final"]==rhs["final"]
        row={"task":i,"saved_target_present":bool(raw),"first_divergent_action_index":first_diverge}
        summary["identical_first_model_request"]+=1
        summary["target_available_to_save"]+=bool(raw)
        summary["tasks_with_changed_read_result"]+=first_diverge is not None
        for arm,trace in [("history",lhs),("pointer",rhs)]:
            n,success=0,0
            for ev in trace["events"]:
                if raw and id_number(ev["decision"])==1:
                    n+=1;s=ev.get("span")
                    success+=int(bool(s and (s["path"],s["center"])==(raw["path"],raw["line"])))
            by_arm[arm]["attempts"]+=n;by_arm[arm]["resolved_reads"]+=success
            by_arm[arm]["tasks_attempted"]+=n>0;by_arm[arm]["tasks_resolved"]+=success>0
            row[arm]={"attempts":n,"resolved_reads":success}
        rows.append(row)
    x.write(x.D/"handle_audit.json",{"summary":dict(summary),"by_arm":by_arm,"rows":rows})
if __name__=="__main__":main()
