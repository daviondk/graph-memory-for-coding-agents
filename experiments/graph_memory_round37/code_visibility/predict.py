"""Prepare predictions before exposing future observations. Only address/hash pairs leave memory."""
from project import D,get,save,sha,h
from collections import Counter,defaultdict
ALG=("F","K","T","H","Tstar","U")
CAP=128

def canonical(items):
    out={int(n):s for n,s in items}
    assert len(out)==len(items)
    return out

def ordered(path,items):
    return sorted(items.items(),key=lambda it:(h("R37-128|"+path+"|"+str(it[0])),it[0]))

def memory(path,past,edit):
    before=dict(ordered(path,canonical(past))[:CAP])
    seen=dict(ordered(path,canonical(edit["rows"]))[:CAP])
    potential={n:s for n,s in before.items() if n not in seen}
    anchor=edit["k"]
    original_kept={};shifted={}
    if anchor is not None:
        end=anchor+edit["old_breaks"]
        for n,s in before.items():
            if anchor<=n<=end:continue
            original_kept[n]=s
            j=n if n<anchor else n+edit["delta"]
            assert j>0 and j not in shifted
            shifted[j]=s
    slots=CAP-len(seen)
    def top(extra,limit=slots):
        return dict(ordered(path,{n:s for n,s in extra.items() if n not in seen})[:limit])
    fixed=top(shifted);same=min(len(fixed),len(potential),slots)
    variants=dict(F={},K=top(potential),T=fixed,H=top(potential,same),Tstar=top(fixed,same),U=top(original_kept))
    views={name:extra|seen for name,extra in variants.items()}
    assert len(views["H"])==len(views["Tstar"])
    assert all(len(v)<=CAP and all(v.get(k)==s for k,s in seen.items()) for v in views.values())
    return views

def main():
    data=get(D/"events.json.gz");seal=get(D/"source-seal.json")
    assert seal["projection"]==sha(D/"events.json.gz") and seal["code"]==sha(D/"project.py")
    out=[];future={};flow=defaultdict(Counter)
    for rid,v in data.items():
        cat="main" if v["subset"] in ("predecessors","main_takeovers") else "secondary"
        count=flow[cat];count["runs"]+=1;state={};last_opaque=-1
        for e in v["events"]:
            idx,kind,*detail=e
            if kind=="barrier":last_opaque=idx;continue
            path=detail[0];key=path
            if kind=="write_start":
                if key in state:state[key]["starts"].append(idx)
            elif kind in ("edit","other"):
                count["successful_file_edits" if kind=="edit" else "other_successful_file_writes"]+=1
                if key in state:state[key]["ops"].append(e)
            elif kind=="read":
                rows=detail[1];count["file_views"]+=1
                old=state.get(key)
                if old is not None:
                    count["consecutive_same_path_views"]+=1
                    if old["ops"]:count["view_pairs_with_any_write"]+=1
                    if len(old["ops"])==1 and old["ops"][0][1]=="edit":
                        count["view_pairs_one_successful_replace"]+=1
                        ed=old["ops"][0];k=ed[3]
                        if old["rows"] and rows and k["matched"] and old["idx"]<k["action_index"]<ed[0]<idx:
                            count["rendered_pair_with_linked_action"]+=1
                            if old["starts"]==[k["action_index"]]:
                                clean=last_opaque<old["idx"];qc="strict" if clean else "opaque"
                                count["classified_"+qc]+=1
                                q=h(rid+"|"+str(old["idx"])+"|"+str(ed[0])+"|"+str(idx))
                                methods=memory(path,old["rows"],k)
                                out.append(dict(q=q,rid=rid,issue=v["issue"],repo=v["repo"],cohort=cat,window=qc,
                                   prev=old["idx"],edit=ed[0],next=idx,path_hash=h(path),source_rows=len(old["rows"]),
                                   anchor=k["k"],delta=k["delta"],receipt_rows=len(k["rows"]),
                                   mem={m:sorted(s.items()) for m,s in methods.items()}))
                                assert q not in future
                                future[q]={"observed":rows,"native_audit":ed[4]}
                state[key]={"idx":idx,"rows":rows,"ops":[],"starts":[]}
    a=save(D/"predictions.json.gz",out);b=save(D/"observations.json.gz",future)
    info=dict(predictions=a,observations=b,flow=flow,projection=seal["projection"],cap=CAP,code=sha(D/"predict.py"),
       protocol=sha(D/"PROTOCOL_RU.md"),capacity_note=sha(D/"CAPACITY_NOTE_RU.md"))
    save(D/"prediction-seal.json",info);print({k:dict(c) for k,c in flow.items()})
if __name__=="__main__":main()
