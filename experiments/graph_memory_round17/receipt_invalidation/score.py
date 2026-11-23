"""Join sealed forecasts to subsequent visible results. No outcome participates in the write/read decision."""
import collections
import random
import re
from observe import ROOT, RECEIPTS, read, put, sha, terminal

def interval(rows, field):
    # Ratio of counts per sampled task, conditional on a nonempty denominator.
    blocks=collections.defaultdict(lambda:[0,0])
    for iid,pos,n in rows:blocks[iid][0]+=pos;blocks[iid][1]+=n
    if not blocks:return None
    rng=random.Random(17137);vals=[];groups=list(blocks.values())
    for _ in range(3000):
        sampled=rng.choices(groups,k=len(groups));den=sum(v[1] for v in sampled)
        if den:vals.append(sum(v[0] for v in sampled)/den)
    vals.sort()
    return [vals[int(.025*(len(vals)-1))],vals[int(.975*(len(vals)-1))]] if vals else None

def main():
    for n,h in read(ROOT/"forecast-seal.json").items():assert sha((ROOT/n).read_bytes())==h
    roster={r["id"]:r for r in read(RECEIPTS/"calls.gz")}
    pairs=read(ROOT/"predictions.gz")
    audit=[]
    for p in pairs:
        a,b=roster[p["old_id"]],roster[p["new_id"]]
        assert a["cmd"]==b["cmd"] and a["iid"]==b["iid"] and a["step"]<b["step"]
        s0,tail0=terminal(a["visible"]);s,tail=terminal(b["visible"])
        if s=="pass" and b["rc"]!=0:s="uncertain"
        if s not in ("pass","fail"):s="uncertain"
        def n_pass(line):
            m=re.search(r"(\d+)\s+passed",line);return int(m[1]) if m else None
        kind="unknown+write" if p["unclassified"] and p["changed_paths"] else "unknown" if p["unclassified"] else "parsed_write" if p["changed_paths"] else "read_only"
        audit.append({**p,"outcome":s,"command":a["cmd"],"old_tail":tail0,"new_tail":tail,"old_rc":a["rc"],"new_rc":b["rc"],"old_pass_count":n_pass(tail0),"new_pass_count":n_pass(tail),"kind":kind})
    stats={}
    for group,rows in {"overall":audit,**{name:[p for p in audit if p["test_key"]["root_panel"]==name] for name in ["testbed","named_repo"]},**{name:[p for p in audit if p["panel"]==name] for name in ["science","other"]}}.items():
        selected={}
        for arm in ("rerun_all","reuse_all","read_only","changed_stem","other_tests_or_docs"):
            used=[p for p in rows if p["predictions"][arm]]
            counts=collections.Counter(p["outcome"] for p in used)
            selected[arm]={"reuse":len(used),"rerun":len(rows)-len(used),"use_outcomes":counts,"reuse_rate_ci":interval([(p["iid"],p["predictions"][arm],1) for p in rows],"reuse"),"false_pass_rate_ci_given_known":interval([(p["iid"],p["predictions"][arm] and p["outcome"]=="fail",p["predictions"][arm] and p["outcome"]!="uncertain") for p in rows],"false")}
        stats[group]={"pairs":len(rows),"tasks":len({p["iid"] for p in rows}),"repos":len({p["repo"] for p in rows}),"levels":collections.Counter(p["test_key"]["level"] for p in rows),"outcomes":collections.Counter(p["outcome"] for p in rows),"phases":{k:collections.Counter(p["outcome"] for p in rows if p["kind"]==k) for k in sorted({p["kind"] for p in rows})},"arms":selected}
    cells=collections.defaultdict(set)
    for p in audit:cells[p["iid"],p["command_sha"]].add(p["kind"])
    stats["diagnostics"]={"same_goal_read_and_write":sum("read_only" in s and any("write" in x for x in s) for s in cells.values()),"different_collected_pass_counts":sum(p["outcome"]=="pass" and p["old_pass_count"]!=p["new_pass_count"] for p in audit),"unclassified":sum(p["unclassified"] for p in audit),"ambiguous_root":sum(p["ambiguous_root"] for p in audit),"parallel":sum(p["parallel"] for p in audit)}
    put("paired-evidence.gz",audit);put("results.json",stats)
    print(stats["overall"]);print(stats["diagnostics"])
if __name__=="__main__":main()
