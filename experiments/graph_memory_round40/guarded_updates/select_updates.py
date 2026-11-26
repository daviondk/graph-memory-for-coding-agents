"""Rerun all three exact packet choices on the same pre-gated pool."""
from collections import Counter
from shared import D,NAT,VF,SPAN,read,signed,sha,save,h,sys
sys.path.insert(0,str(NAT))
from score import select


def main():
    guarded=read(D/"guarded-plans.json.gz")
    assert sha(D/"guarded-plans.json.gz")==read(D/"plan-seal.json")["plans"]
    original=signed(NAT,"plans.json.gz")
    operations=signed(SPAN,"scored.json.gz")
    held=set(signed(VF,"prediction-seal.json")["test_issues"])
    records=[]
    for op in operations:
        run,at=op["rid"],op["event"]
        inc,rem=guarded[run][str(at)];old=original[run][str(at)]
        pool=[(idx,path,size,value) for idx,path,lo,hi,size,value,view in inc]
        edited=op["path"]
        affected={idx for idx,path,lo,hi,size,value,view in inc if path==edited}
        overlapping={idx for idx,path,lo,hi,size,value,view in inc if path==edited and lo<=op["end"] and hi>=op["start"]}
        chosen,_,_=select(pool)
        moved,head,_=select([v for v in pool if v[0] not in overlapping])
        full,_,_=select([v for v in pool if v[0] not in affected])
        # Compare packet IDs and order; separately record whether coordinates move.
        same=(chosen==moved);file_same=(chosen==full)
        certificate=not overlapping.intersection(chosen) and set(head).issubset(chosen)
        assert same==certificate
        removed={i for i,reason,view in rem}
        costs=Counter(all_pool_rows=sum(b[2]-b[1]+1 for b in old),all_pool_bytes=sum(b[3] for b in old),
            removed_rows=sum(old[i][2]-old[i][1]+1 for i in removed),removed_bytes=sum(old[i][3] for i in removed),
            all_pool_blocks=len(old),removed_blocks=len(removed),old_selected_bytes=sum(old[i][3] for i in chosen),
            after_interval_selected_bytes=sum(old[i][3] for i in moved),after_file_selected_bytes=sum(old[i][3] for i in full),
            unfiltered_selected_bytes=op["bytes"],old_selected_affected=sum(i in affected for i in chosen))
        old_ids=set(chosen)
        costs["unchanged_selected_bytes"]=sum(old[i][3] for i in old_ids.intersection(moved))
        stable=same and not any(i in old_ids and old[i][1]>op["end"] and op["delta"]!=0 for i in affected)
        records.append(dict(run=run,at=at,receipt=op["receipt"],view=op["view"],issue=h(op["issue"]),group=op["group"],held=int(h(op["issue"]) in held),
            path=edited,start=op["start"],end=op["end"],delta=op["delta"],pool=len(pool),old=list(chosen),interval=list(moved),file=list(full),
            same=int(same),file_same=int(file_same),stable=int(stable),cost=costs))
    save(D/"selections.json.gz",records)
    save(D/"selection-seal.json",dict(records=len(records),selection=sha(D/"selections.json.gz"),plans=sha(D/"plan-seal.json"),
        source_geometry=sha(SPAN/"scored.json.gz"),solver=sha(NAT/"score.py"),code=sha(D/"select_updates.py")))
    print("Selected",len(records),sha(D/"selections.json.gz"))


if __name__=="__main__":
    main()
