"""Secondary crossed bootstrap of trajectories and four held-transfer encoder seeds."""
from audit import *
def main():
    flags=get(HERE/"candidate-flags.json.gz"); ids=get(HERE/"identities.json.gz"); records=get(HERE.parent/"calibration_transfer/outcomes.json.gz")
    qz=ids["q"];tz=ids["t"]; iq=set().union(*(set(tz[v["t"]]["intent_norm"]) for v in qz.values() if v["s"]!="test"));gq=set().union(*(set(v["gold_norm"]) for v in qz.values() if v["s"]!="test"))
    selected={"all":sorted(records),"new_intent_quote_goldunits":sorted(q for q,r in records.items() if not (set(tz[r["t"]]["intent_norm"])&iq or set(qz[q]["gold_norm"])&gq or flags[q]["any_gold_unit_seen_in_prior_pool"])),"all_pool_units_new":sorted(q for q in records if not flags[q]["any_pool_text_seen"])}
    out={};base=get(HERE/"audit-results.json")
    for k,qs in selected.items():
        assert len(qs)==base["subsets"][k]["q"];labels,idx=np.unique([records[q]["t"] for q in qs],return_inverse=True);n=len(labels);cnt=np.bincount(idx); raw=np.array([[np.subtract(z["oof_3894"][:3],z["original_R33"][:3])*100 for s in ("17","29","37","41") for z in [records[q]["seeds"][s]]] for q in qs])
        aa=np.zeros((n,4,3));np.add.at(aa,idx,raw);rng=np.random.default_rng(835035);boot=[]
        for _ in range(100):
            ix=rng.integers(0,n,size=(100,n)); sx=rng.integers(0,4,(100,4));per=aa[ix].sum(axis=1)/cnt[ix].sum(axis=1)[:,None,None];boot.extend(per[np.arange(100)[:,None],sx].mean(axis=1))
        out[k]={"transfer4_delta":raw.mean(axis=(0,1)).tolist(),"transfer4_crossed_ci":np.quantile(boot,[.025,.975],axis=0).T.tolist()}
    save(HERE/"crossed.json",out);print(out)
if __name__=="__main__":main()
