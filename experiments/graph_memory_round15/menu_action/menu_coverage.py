"""Input-only diagnosis of which interventions can change in each fixed-size menu."""
from collections import Counter
from menu import D,F,LOCK,ARMS,h,lock,read,put
def main():
    assert h((F/"forecast.lock.json").read_bytes())==LOCK
    lock(F/"forecast.lock.json")
    ranks=read(F/"forecasts.json.gz");selected={r["id"] for r in read(D/"menus.json.gz")}
    out={}
    for panel,rows in ranks.items():
        results={}
        for k in (1,3,6,10):
            summary=Counter()
            for row in rows:
                preds={p:row["ranks"][p][:k] for p in ARMS}
                summary["all_anchors"]+=1
                if len(preds["flat_union"])==k and len(preds["typed_union"])==k:
                    summary["two_full"]+=1
                    if set(preds["typed_union"])!=set(preds["flat_union"]):summary["two_full_changed_membership"]+=1
                if not all(len(x)==k for x in preds.values()):continue
                summary["all_three_full"]+=1
                if preds["typed_union"]!=preds["flat_union"]:summary["typed_flat_order_or_membership"]+=1
                if set(preds["typed_union"])!=set(preds["flat_union"]):summary["typed_flat_membership_changed"]+=1
                if set(preds["typed_union"])!=set(preds["view_graph"]):summary["typed_view_membership_changed"]+=1
                if row["id"] in selected:
                    summary["selected_at_six_supported_at_k"]+=1
                    if preds["typed_union"]!=preds["flat_union"]:summary["selected_typed_flat_order_or_membership"]+=1
                    if set(preds["typed_union"])!=set(preds["flat_union"]):summary["selected_typed_flat_membership_changed"]+=1
            results[k]=summary
        out[panel]=results
    put(D/"coverage_by_k.json",out)
    for p,a in out.items():print(p,dict(a[6]),flush=True)
if __name__=="__main__":main()
