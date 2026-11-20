"""Independent invariants over all released predictions and an overlap check on archived R2-F outputs."""
import gzip,itertools,json,statistics,sys
from collections import Counter,defaultdict
from context import D,F,e,rows,stream,prev,read,save,h,np,atomic_line
from predict import at_cut
def coords(record):return {(p,z) for p,a,b in record[0] for z in range(a,b+1)}
def old_replay():
    m=read("fine_model.json");m["lookup"]={k:j for j,k in enumerate(m["length_dist"])};m["cdfs"]=np.asarray(list(m["length_dist"].values()))
    origin=(prev.read("width_model.json"),e.read("model.json")["flat"],prev.read("offset.json")["intercept"])
    verified=0;checked_prefixes=0
    for k in range(8):
        archived={(i,t):v for i,t,cc,v in rows(F/f"budget_pred_{k}.jsonl.gz")}
        obj=next(iter(rows(F/f"fresh_{k}.jsonl.gz")))
        for t,rr,idx,meta,hist,last in itertools.islice(stream(obj),3):
            a=at_cut(obj,t,rr,idx,meta,hist,last,m,origin)
            trunc={**obj,"events":obj["events"][:t]+[["other",{},""]]}
            t2,rr2,idx2,mt2,hs2,ls2=list(stream(trunc))[-1]
            # Only current observation state and issue may affect a decision.
            assert t==t2 and rr==rr2 and idx==idx2 and hist==hs2 and last==ls2 and meta==mt2
            checked_prefixes+=1
            for B in (256,512):
                for prior,current in (("typed","r2f"),("recent","recent")):
                    sel,c,w=archived[obj["instance"],t][str(B)][prior]
                    mapped=[[rr[j][0],rr[j][1],rr[j][2]] for j in sel]
                    assert a[B][current]==[mapped,c,w];verified+=1
    return verified,checked_prefixes
def main():
    a=read("selection.json");b=json.loads((D/"replication/selection.json").read_bytes())
    ia={x[0] for x in a};ib={x[0] for x in b}
    repos=lambda s:{i.split(".")[0] for i in s}
    train=set(e.read("split.json")["all"])-set(e.read("split.json")["test"])
    assert not (repos(ia)&repos(ib) or train&(repos(ia)|repos(ib)) or ia&ib)
    receipt={"train_projects":len(train),"new_projects":[len(repos(ia)),len(repos(ib))],"shared_projects":0,"shared_instances":0,"sources":{}}
    for root in [D,D/"replication"]:
        checked=0;invariants=0;cuts=0
        for k in range(8):
            base=rows(root/f"pred_{k}.jsonl.gz");extended=rows(root/f"expand_pred_{k}.jsonl.gz")
            for x,y in zip(base,extended,strict=True):
                assert x[:2]==y[:2];cuts+=1
                for B in [256,512]:
                    orig=x[2][str(B)];new=y[2][str(B)];old=orig["r2f"]
                    assert old==new["r2f"] and orig["typed"]==new["typed"]
                    assert coords(old)==coords(new["coalesce"])
                    for a,v in [("old_balanced","r2f"),("old_forward","r2f"),("recent_balanced","recent"),("typed_balanced","typed"),("iso_balanced","r2f"),("iso_forward","r2f")]:
                        assert coords(orig[v])<=coords(new[a]);invariants+=1
                        if a.startswith("iso"):
                            assert new[a][1]<=old[1] and new[a][2]<=old[2];checked+=1
        receipt["sources"][root.name]={"cuts":cuts,"monotonic_coverage_assertions":invariants,"double_cost_envelope_checks":checked}
    receipt["archived_r2f_selections_and_prices"],receipt["prefix_invariance_checks"]=old_replay()
    save("audit.json",receipt)
if __name__=="__main__":main()
