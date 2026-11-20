"""Secondary multiplicity and influence sensitivity for the predeclared QA outcomes."""
import itertools
import json
from pathlib import Path

here = Path(__file__).resolve().parent
retrieval = json.loads((here / "retrieval_results.json").read_text("utf8"))["results"]
conversational = json.loads((here / "conversational_results.json").read_text("utf8"))
families = {
    "two_original_primary":{key:row["contrasts"]["flat"]["all@5"] for key,row in retrieval.items()},
    "four_transferred_query_styles":{key:row["graph_minus_flat"]["all@5"] for key,row in conversational.items()},
}
report={}
for family,rows in families.items():
    ordered = sorted(rows, key=lambda k:rows[k]["p_cluster"])
    upper=0
    results={}
    for idx,k in enumerate(ordered):
        row=rows[k]
        groups=row["by_conversation"]
        delta=[round(x["n"]*x["delta"]) for x in groups.values()]
        size=[x["n"] for x in groups.values()]
        assert sum(size) == row["n"]
        assert sum(delta) == row["wins"]-row["loss"]
        observed=abs(sum(delta))
        all_signs=list(itertools.product((-1,1),repeat=len(delta)))
        p=sum(abs(sum(s*v for s,v in zip(sign,delta)))>=observed for sign in all_signs)/len(all_signs)
        assert p==row["p_cluster"]
        upper=max(upper,min(1.0,(len(ordered)-idx)*p))
        leave_out=[(sum(delta)-v)/(sum(size)-n) for v,n in zip(delta,size)]
        results[k]={"p_exact_sign_flip":p,"holm_within_family":upper,"leave_one_dialog_out_delta":[min(leave_out),max(leave_out)],"groups":len(delta),"positive_groups":sum(v>0 for v in delta),"ties":delta.count(0)}
    report[family]=results
(here/"family_results.json").write_text(json.dumps(report,indent=2),encoding="utf8")
print(json.dumps(report,indent=2))
