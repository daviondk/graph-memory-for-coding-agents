"""Replay the prespecified gate using actual per-arm responses and condition on the stratum-specific reading budget."""
from collections import Counter, defaultdict
from fractions import Fraction
import datetime
import json
import math
from pathlib import Path
from audit_reader import HERE, check, digest, exact_discordants, read


def exact_budget(rows, gate):
    strata = defaultdict(list)
    for row in rows:
        l, e = row["arms"]["local"], row["arms"]["edge"]
        if l["cid"] != e["cid"]:
            strata[row["panel"]].append((int(e["em"])-int(l["em"]), gate[row["id"]]))
    dist = {0:Fraction(1)}
    for group in strata.values():
        n = len(group); k=sum(use for _,use in group)
        signs = Counter(delta for delta,_ in group)
        counts = Counter()
        for wins in range(min(k, signs[1])+1):
            for losses in range(min(k-wins,signs[-1])+1):
                ties = k-wins-losses
                if ties <= signs[0]:
                    counts[wins-losses] += math.comb(signs[1],wins)*math.comb(signs[-1],losses)*math.comb(signs[0],ties)
        denom = math.comb(n,k)
        assert sum(counts.values())==denom
        combined = defaultdict(Fraction)
        for x,a in dist.items():
            for y,b in counts.items():
                combined[x+y] += a*Fraction(b,denom)
        dist=combined
    assert sum(dist.values())==1
    observed=sum(delta*use for group in strata.values() for delta,use in group)
    tail=sum(p for x,p in dist.items() if x>=observed)
    return {"observed_improvement_count":observed,"p_one_sided_random_policy_ge":float(tail),"p_exact_fraction":str(tail),
            "expected_random_improvement_count":float(sum(int(x)*v for x,v in dist.items())),
            "counts_by_stratum":{s:[sum(use for _,use in v),len(v)] for s,v in sorted(strata.items())},
            "distribution":{k:str(v) for k,v in sorted(dist.items())}}


def run(panel):
    rows=read(HERE/f"{panel}_audit_items.json.gz"); ast=read(HERE/"ast_roles.json")["records"][panel]
    gate={r["id"]:ast.get(r["id"],{}).get("strong",False) for r in rows}
    assert all(not gate[r["id"]] or r["arms"]["edge"]["cid"]!=r["arms"]["local"]["cid"] for r in rows)
    n=len(rows)
    def options(row):
        arms=row["arms"]
        return {"local":arms["local"],"edge":arms["edge"],"ast_gate":arms["edge" if gate[row["id"]] else "local"]}
    selections=[options(r) for r in rows]; methods={}
    for a in ("local","edge","ast_gate"):
        vals=[m[a] for m in selections]
        methods[a]={"em_count":sum(v["em"] for v in vals),"em_percent":100*sum(v["em"] for v in vals)/n,
                    **{field:sum(v[field] for v in vals)/n for field in ("es","id_f1","prompt_tokens","evidence_tokens")}}
    paired={}
    for name in ("local","edge"):
        group = [(m["ast_gate"],m[name]) for m in selections]
        plus=sum(l["em"]>r["em"] for l,r in group); minus=sum(l["em"]<r["em"] for l,r in group)
        paired[name]={"wins":plus,"losses":minus,"delta_em_pp":100*(plus-minus)/n,"p_mcnemar_twosided":exact_discordants(plus,minus)}
    by_role=defaultdict(Counter)
    for r in rows:
        role=ast.get(r["id"],{}).get("primary","no_edge")
        e,l=r["arms"]["edge"],r["arms"]["local"]
        by_role[role].update({"n":1,"wins":e["em"]>l["em"],"losses":e["em"]<l["em"],"es_change":e["es"]-l["es"]})
    return {"n":n,"switched":sum(gate.values()),"methods":methods,"gate_vs":paired,"random_matched":exact_budget(rows,gate),
            "exploratory_roles":dict(by_role)}

def main():
    lock=read(HERE/"ast_gate_lock.json")
    for p in lock["files"]:
        check(digest(HERE / p["Path"].replace(chr(92),"/").split("/")[-1]).upper()==p["Hash"],"gate lock mismatch")
    out={k:run(k) for k in ("A","B")}
    out["utc"]=datetime.datetime.now(datetime.UTC).isoformat()
    out["script_sha256"]=digest(Path(__file__))
    (HERE/"ast_gate_results.json").write_text(json.dumps(out,indent=2),encoding="utf8")
    for k in ("A","B"):
        z=out[k];print(k,z["switched"],z["methods"],z["gate_vs"],z["random_matched"]["p_one_sided_random_policy_ge"])
if __name__=="__main__":
    main()

