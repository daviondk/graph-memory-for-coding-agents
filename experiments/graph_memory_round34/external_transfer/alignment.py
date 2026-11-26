"""Hold file multiplicities fixed and destroy only the binding of historical features to candidate paths."""
from experiment import *
from collections import defaultdict
from hashlib import sha256
def main():
    b=HERE/"strong";model=read(b/"models.json")[read(b/"selection.json")["modes"]["union_cost"]]
    data={q:r for q,r in read(b/"features.json.gz").items() if r["split"]=="test"}
    source={r["state_id"]:r for r in rows(PUB/"items.jsonl.gz") if r["state_id"] in data}
    expected=read(b/"test-ranks.json.gz");codes={};ever=0; changed=0
    for q,r in data.items():
        paths_by={c["evidence_id"]:norm(c["source_path"]) for c in source[q]["candidate_evidence"]}
        loc=defaultdict(list)
        for i,k in enumerate(r["ids"]):loc[paths_by[k]].append(i)
        by_size=defaultdict(list)
        for k,v in sorted(loc.items()):by_size[len(v)].append(v)
        x=np.array(r["x"]); feats=x[:,2:].copy();o=np.array(r["off"]);mu=np.array(model["center"]);sc=np.array(model["scale"]);w=np.array(model["weights"])
        for v in loc.values():assert np.all(feats[v]==feats[v[:1]])
        assert np.argsort(-(o+(x-mu)/sc@w),kind="stable").tolist()==expected[q]["union_cost"]
        reps=[];alters=0
        for seed in range(64):
            rng=np.random.default_rng(int.from_bytes(sha256(f"ser-align/{seed}/{q}".encode()).digest()[:8],"little"))
            for paths1 in by_size.values():
                perm=rng.permutation(len(paths1))
                for j,a in enumerate(paths1):x[a,2:]=feats[paths1[perm[j]]]
            alters+=int(np.any(x[:,2:]!=feats));ix=np.argsort(-(o+(x-mu)/sc@w),kind="stable")[:8]
            reps.append(ix.tolist())
        changed+=alters;ever+=bool(alters);codes[q]=reps
    dst=HERE/"alignment-ranks.json.gz";save(dst,codes);save(HERE/"alignment-seal.json",{"forecasts":sha(dst),"protocol":sha(HERE/"ALIGNMENT_RU.md"),"model_selection":sha(b/"selection.json"),"code":sha(Path(__file__))})
    gold=split_gold(set(data));original=read(b/"test-outcomes.json.gz");ag={};groups=defaultdict(list);repmeans=[];scores_all=[]
    for q,seqs in codes.items():
        cache={};v=[]
        for seq in seqs:
            k=tuple(seq)
            if k not in cache:cache[k]=score(data[q],np.array(seq),gold[q])
            v.append(cache[k])
        v=np.array(v);scores_all.append(v[:,0]);a=np.mean(v,axis=0);y=original[q]["arms"]["union_cost"];ag[q]=[data[q]["repo"],a.tolist(),y];groups[data[q]["repo"]].append(y-a)
    save(HERE/"alignment-outcomes.json.gz",ag);ordered=sorted(groups);n=len(ordered);sizes=np.array([len(groups[k]) for k in ordered]);sums=np.array([np.sum(groups[k],axis=0) for k in ordered])
    rng=np.random.default_rng(34);boot=[]
    for _ in range(100):
        ix=rng.integers(n,size=(100,n));boot.extend(sums[ix].sum(1)/sizes[ix].sum(1)[:,None])
    save(HERE/"alignment.json",{"changed_states":ever,"changed_state_permutations":changed,"total_state_permutations":64*len(data),
        "average_shuffled":np.mean([v[1] for v in ag.values()],axis=0).tolist(),"difference":(sums.sum(0)/sizes.sum()).tolist(),
        "ci95":np.quantile(boot,[.025,.975],axis=0).tolist(),"per_seed_primary":np.mean(scores_all,axis=0).tolist(),"seal":sha(HERE/"alignment-seal.json")})
if __name__=="__main__":main()
