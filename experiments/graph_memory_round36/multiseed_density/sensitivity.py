"""Independent question-wise reconstruction from the immutable coupled forecast rows."""
from summarize_density import *
def main():
    geo={};out=load(D/"outcomes.json.gz");target=load(D.parent/"multiseed_midpoint/outcomes.json.gz");eligible=sorted(q for q,v in target.items() if v["eligible"] and not v["pilot"]);counts=D.parent/"edge_count_control";plans=load(D/"plan.json");arms=plans["arms"];result={};main=load(D/"results.json")["panels"]["primary"]
    for i in range(8):geo.update(load(counts/f"edges-{i}.json.gz"))
    for ix,f,opt in [(0,"G","global_choice"),(1,"T","target_choice")]:
        old=np.array([[[target[q]["seeds"][str(s)]["M"][0] for salt in SALTS] for s in SEEDS] for q in eligible])
        actual=np.array([[[out[q]["values"][out[q]["seeds"][str(s)][arms.index(f+"_"+salt)]][0] for salt in SALTS] for s in SEEDS] for q in eligible]);diff=(old-actual)*100.;strict=np.array([geo[out[q]["t"]][opt] for q in eligible]);assert not np.any(diff[~strict]);assert np.isclose(diff.mean(),main["delta"][ix][0]);ts,lab=np.unique([out[q]["t"] for q,k in zip(eligible,strict) if k],return_inverse=True)
        d=diff[strict].mean(axis=2);clusters=np.zeros((len(ts),4));np.add.at(clusters,lab,d);nq=np.bincount(lab);rng=np.random.default_rng(362801);rr=[]
        for _ in range(100):
            tj=rng.integers(len(ts),size=(100,len(ts)));sj=rng.integers(4,size=(100,4));v=clusters[tj].sum(axis=1)/nq[tj].sum(axis=1)[:,None];rr.extend(v[np.arange(100)[:,None],sj].mean(axis=1))
        supports={out[q]["t"] for q in eligible};sets=np.array([len({tuple(geo[t]["draws"][f+"_"+salt]) for salt in SALTS}) for t in supports])
        result[f]={"distinct_masks_across_eight_on_primary_histories":{str(k):int((sets==k).sum()) for k in range(1,9)},"questions_with_any_FS_difference_across_4x8":int((diff!=0).any(axis=(1,2)).sum()),"M_only_success":int((diff>0).sum()),"control_only_success":int((diff<0).sum()),"MC_salt_sd_contrast_pp":float(diff.mean(axis=(0,1)).std(ddof=1)),"MC_salt_se_pp":float(diff.mean(axis=(0,1)).std(ddof=1)/np.sqrt(8)),"conditional_on_possible_redraw":{"q":int(strict.sum()),"t":len(ts),"delta_pp":float(d.mean()),"crossed_ci":np.quantile(rr,[.025,.975]).tolist()}}
    save(D/"sensitivity.json",result);print(result)
if __name__=="__main__":main()
