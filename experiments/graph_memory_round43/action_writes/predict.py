import time
from collections import Counter
from shared import *
from materialize import boundaries,choose


def main():
    assert sha(D/"PROTOCOL_RU.md")=="f433055bc424a6749b25ced549b2a16929e4582a6dd010f179c52c31c0a53199"
    literal=module("original_literal",W/"memory_session5/packets/common.py")
    sys.path.insert(0,str(V))
    from detector import gate
    from examine import display
    source=module("r37_visible",H/"project.py")
    features=signed(P,"features.json.gz");ev=signed(G,"selections.json.gz");before=signed(F,"packets.json.gz")
    inp=collect(ev);out={};starttime=time.perf_counter()
    for row in ev:
        rid=row["run"];at=row["at"];key=h(rid+"/"+str(row["receipt"]))
        obs=inp[rid][row["view"]];action=inp[rid][at];returned=inp[rid][row["receipt"]]
        assert obs["command"]=="view" and action["command"]==returned["command"]=="str_replace" and not returned["is_error"]
        assert obs["path"]==action["path"]==returned["path"]
        text,_,_=display(obs);mask,_=gate(obs);safe={n:t for n,t in text.items() if mask[n][2]}
        printed=source.numbered(source.textof(returned),returned["path"],True)
        receipt={n:h(t) for n,t in printed.items() if source.informative(t)}
        assert dict(before[key]["receipt"])==receipt
        old,new=action["old_str"],action["new_str"];assert old
        start=row["start"];end=start+new.count("\n")
        assert end==row["end"]+row["delta"]
        base={n:(d,z) for b in features[key]["blocks"] if b["target"] for n,d,z in b["lines"]}
        mem={n:(t,0) for n,t in safe.items()}
        reb=literal.update_literal(mem,old,new,printed,1)
        inner,bound=boundaries(old,new,start,safe)
        fresh={"prior":{},"verbatim":{n:t for n,t in enumerate(new.split("\n"),start)},
               "rebase":{n:t for n,(t,age) in reb.items() if age==1},"interior":inner,"boundary":bound}
        results={};allocations={}
        for m,lines in fresh.items():
            # Safe bound evidence already in the prior bank has precedence on conflicts.
            bank=dict(base);tally=Counter();published=[]
            for n,t in sorted(lines.items()):
                dg=h(t);size=len(t.encode());inform=source.informative(t)
                published.append([n,dg,size,int(inform)])
                tally["all_written"]+=1;tally["written_bytes"]+=size+1
                if not inform:continue
                tally["informative"]+=1
                if n in printed:
                    if printed[n]!=t:tally["receipt_conflicts"]+=1
                    else:tally["duplicate_receipt"]+=1
                    continue
                if n in base:
                    tally["prior_same" if base[n][0]==dg else "prior_conflicts"]+=1
                else:bank[n]=(dg,size);tally["new_to_base"]+=1
            candidate=[[n,d,sz] for n,(d,sz) in bank.items() if n not in printed]
            packs={str(cap):choose(candidate,start,end,cap) for cap in BUDGETS}
            assert all(sum(x[2]+1 for x in v)<=int(c) for c,v in packs.items())
            tally["eligible_lines"]=len(candidate)
            results[m]={"proposed":published,"counts":dict(tally),"packs":packs}
        out[key]=dict(group=row["group"],held=row["held"],issue=row["issue"],repo=features[key]["repo"],methods=results,
            receipt=sorted(receipt.items()),proper_old_match=bool(reb),prior_visible_bytes=sum(1+len(t.encode()) for t in safe.values()),
            action_bytes=len(old.encode())+len(new.encode()))
    save("forecasts.json.gz",out)
    save("forecast-seal.json",dict(sha=sha(D/"forecasts.json.gz"),source=sha(RAW/"files.json"),
         prior=sha(P/"features.json.gz"),registered=sha(D/"PROTOCOL_RU.md"),code={p:sha(D/p) for p in ("predict.py","shared.py","materialize.py")},
         official={str(path.relative_to(W).as_posix()):sha(path) for path in (W/"memory_session5/packets/common.py",H/"project.py",V/"detector.py")},
         selection_and_encoding_s=time.perf_counter()-starttime))
    print("Frozen new source material and budgets",len(out),"observations.")
if __name__=="__main__":main()

