"""Determine which of the minimal groups sets the completion time of the locked reader."""
from geometry import *
def main():
    final={};fit=load(D/"models.json");n=load(D/"selection.json")["chosen"]["witness"];m=fit["models"][n]
    for stage in ("train","dev","test"):
        at=load(D/(stage+"-atoms.json.gz"));out={};cnt=Counter()
        for r in feature(stage):
            q=r["q"];gs=buckets(at[q]);x=np.asarray(r["x"]);v=np.asarray(r["o"])+(x-m["center"])/m["scale"]@m["weights"];rank=np.argsort(ranks(v))
            if not any(len(g)>1 for g in gs):continue
            minima=[min(rank[i] for i in g) for g in gs];critical=[g for g,z in zip(gs,minima) if z==max(minima)]
            multi=any(len(g)>1 for g in critical);entire=all(len(g)>1 for g in critical)
            cnt["alternative_group"]+=1;cnt["alternative_group_binds"]+=multi;cnt["only_alternative_groups_bind"]+=entire
            out[q]=dict(minimal=gs,first_ranks=[int(z)+1 for z in minima],critical=critical)
            if stage=="train":
                out[q]["scores"]={str(i):float(v[i]) for g in gs for i in g}
        final[stage]=dict(counts=dict(cnt),cases=out)
    save(D/"binding.json",final);print({s:v["counts"] for s,v in final.items()})
if __name__=="__main__":main()