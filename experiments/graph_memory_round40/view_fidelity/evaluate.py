from collections import Counter,defaultdict
from data import D,SPAN,read,save,sha,h,split


def main():
    seal=read(D/"prediction-seal.json")
    assert sha(D/"predictions.json.gz")==seal["predictions"] and sha(D/"detector.py")==seal["code"]
    pred=read(D/"predictions.json.gz")
    table={};by_issue={};cases=defaultdict(Counter);native=Counter()
    results={}
    all_rows,_=split()
    group={(r["rid"],r["event"]):r for r in all_rows}
    for stage in ("discovery","holdout"):
        for rid,e,issue,f,category,offset,inside,nlines in read(D/(stage+"-verified.json.gz")):
            k=rid,e,f["n"]
            assert k not in table
            table[k]=(issue,f["line_probe_hash"],category)
    counts=defaultdict(Counter);issues=defaultdict(set);bad_issues=defaultdict(set)
    for rid,e,n,i,test,selected,dig,mask in pred:
        issue,check,cat=table.pop((rid,e,n))
        assert issue==i and dig==check
        ok=cat=="literal"
        stage="holdout" if test else "discovery"
        for pop in ["all"]+(["fully_reused_selected"] if selected else []):
            for splitname in (stage,"pooled"):
                issues[splitname,pop].add(i)
                if not ok:
                    bad_issues[splitname,pop].add(i)
                for name,accept in zip(("all","reject_whole_view","reject_suffix"),mask):
                    counts[splitname,pop,name]["accepted_correct" if accept and ok else "accepted_bad" if accept else "rejected_correct" if ok else "rejected_bad"]+=1
        if selected:
            cases[rid,e]["selected"]+=1
            cases[rid,e]["bad"]+=int(not ok)
            cases[rid,e]["veto"]+=int(not mask[2])
        native["lines"]+=1
        native["prior_mismatch"]+=int(not ok)
        native["reused_selected_lines"]+=selected
        native["reused_selected_post_mismatch"]+=int(selected and not ok)
    assert not table
    source=read(SPAN/"audit_strict.json")["counts"]
    assert all(source[k]==v for k,v in native.items())
    for (s,p,name),v in counts.items():
        results.setdefault(s,{}).setdefault(p,{})[name]={k:v[k] for k in ("accepted_correct","accepted_bad","rejected_correct","rejected_bad")}
    for (s,p),iq in issues.items():
        results[s][p]["issues"]=len(iq)
        results[s][p]["issues_with_mismatch"]=len(bad_issues[s,p])
    packet=defaultdict(Counter)
    for r in all_rows:
        if not r["range_reuse"]:
            continue
        v=cases[r["rid"],r["event"]]
        s="holdout" if h(r["issue"]) in seal["test_issues"] else "discovery"
        for stage in (s,"pooled"):
            pp=packet[stage]
            pp["structurally_reused_packets"]+=1
            pp["no_selected_affected_line"]+=int(not v["selected"])
            pp["packets_with_mismatched_selected_lines"]+=int(bool(v["bad"]))
            pp["packets_vetoed_by_gate"]+=int(bool(v["veto"]))
            pp["erroneous_packets_accepted"]+=int(bool(v["bad"]) and not v["veto"])
    save(D/"results.json",dict(tables=results,packet=packet,reference_totals=native,forecast=sha(D/"prediction-seal.json"),
        issue_split="every third in SHA256 order",provenance=sha(SPAN/"audit_strict.json")))
    print(results["holdout"],dict(packet))


if __name__=="__main__":
    main()
