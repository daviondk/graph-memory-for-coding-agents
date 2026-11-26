"""Every path is gated before the edited path or its receipt geometry is supplied."""
from collections import Counter
from shared import D,W,VF,NAT,R38,read,save,sha,raw_events,signed,sys
from detector import gate
from examine import display
sys.path.insert(0,str(NAT))
from project import chunk


def main():
    assert sha(D/"PROTOCOL_RU.md")=="ea4754edffb9283172c07bc49beb5ae9a1a6020f1897ed5ef835f072cec84802"
    vf=read(VF/"manifest.json")["files"]
    assert all(sha(VF/f)==vf[f] for f in ("detector.py","examine.py","data.py"))
    schema=signed(R38,"schedule.json.gz")
    visible=signed(R38,"visible.json.gz")
    orig=signed(NAT,"plans.json.gz")
    needed=[{"rid":run,"view":ev[0]} for run,meta in schema.items() for ev in meta["events"] if ev[1]=="view"]
    src=raw_events(needed,receipts=False)
    plans={};counts=Counter()
    for run,meta in schema.items():
        active={};run_plans={}
        for ev in meta["events"]:
            at,kind=ev[:2]
            if kind=="reset":
                active.clear()
                continue
            path=ev[2]
            if kind=="view":
                obs=src[run][at]["observation"]
                facts=visible[run][str(at)]
                text,headers,_=display(obs)
                mask,cut=gate(obs)
                from data import h
                valid=(headers==1 and [[n,h(v),len(v.encode()),int(n+1 in text)] for n,v in sorted(text.items())]==facts)
                prev=active.get(path)
                active[path]=(at,1+prev[1] if prev else 1,chunk(facts),{n:bool(flags[2]) for n,flags in mask.items()} if valid else {})
                counts["raw_views"]+=1
                counts["recognized_views"]+=int(valid)
                continue
            old=orig[run][str(at)]
            # Rebuild the latest view for all paths. Match full public rank/cost identities before filtering.
            reconstructed=[]
            for addr,(view,hits,blocks,mask) in sorted(active.items(),key=lambda t:(-t[1][0],t[0])):
                for lo,hi,size in blocks:
                    index=len(reconstructed)
                    score=1+32*min(8,hits)+128//(index+1)
                    reconstructed.append((addr,lo,hi,size,score,view,hits,mask))
            same=len(old)==len(reconstructed)
            included=[];removed=[]
            for index,block in enumerate(old):
                ref=reconstructed[index] if same else None
                if ref is None or list(ref[:5])!=block or any(n not in ref[7] for n in range(block[1],block[2]+1)):
                    removed.append([index,"unresolved",None])
                    counts["unresolved_blocks"]+=1
                elif not all(ref[7][n] for n in range(block[1],block[2]+1)):
                    removed.append([index,"gate",ref[5]])
                    counts["clip_rejected_blocks"]+=1
                else:
                    rank=len(included)
                    utility=1+32*min(8,ref[6])+128//(rank+1)
                    included.append([index,*block[:4],utility,ref[5]])
                    counts["included_blocks"]+=1
            counts["plans"]+=1
            run_plans[at]=[included,removed]
            active.pop(path,None)
        plans[run]=run_plans
    dst=D/"guarded-plans.json.gz";save(dst,plans)
    save(D/"plan-seal.json",dict(plans=sha(dst),counts=counts,source_plans=sha(NAT/"plans.json.gz"),schedule=sha(R38/"schedule.json.gz"),
        guard=sha(VF/"manifest.json"),registered=sha(D/"PROTOCOL_RU.md"),implementation=sha(D/"plan.py")))
    print(counts)


if __name__=="__main__":
    main()
