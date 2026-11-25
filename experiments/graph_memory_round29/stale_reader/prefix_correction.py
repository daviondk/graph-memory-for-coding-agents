"""Audited prefix protocol. Assemble blind amendments before opening any forecast or evaluation file."""
from actor_inputs import SYS,bind
from retrieve29 import chunks,make_slots,Tokenizer,QWT
from setup29 import D,P,Path,h,sha,read,save
def prepare():
    audit=read(D/"blind-audit.json");assert not audit["late_addresses"] and not audit["slot_mismatches"]
    slots=read(P/"retrieval-strings.json.gz");prev=read(D/"retrieval.json.gz")
    lastinputs=read(P/"actor-requests.json.gz");original=read(D/"actor-assignment.json.gz")
    ass={q:a.copy() for q,a in original.items()};req=dict(lastinputs)
    changed=read(P/"early-hardened-differences.json.gz");qs=read(P/"reader-questions.json");hh=read(P/"reader-histories.json.gz");tok=Tokenizer.from_file(str(QWT))
    amended={};physical_prefix=0;retro=0
    for q,proof in audit["cases"].items():
        assert proof["bm_equal"]
        if q in changed:slots[q]=changed[q];physical_prefix+=1
        sp=qs[q];case=sp["case"];target=next(k for k,r in qs.items() if r["case"]==case and r["asof"]==sp["asof"] and r["available_until"]>sp["available_until"])
        rows=chunks(hh[case],tok);rr={(z["source"],z["start"]):i for i,z in enumerate(rows)}
        desired={"H":slots[target]["H"],**{a:slots[q][a] for a in ("T","G")}}
        indices={a:[rr[(z["source"],z["origin"])] for z in zz] for a,zz in desired.items()}
        new=make_slots(indices,rows,tok)
        if slots[target]!=new:retro+=1;slots[target]=new
    for q in slots:
        for arm,ls in slots[q].items():
            st=bind(qs[q]["ask"],[z["text"] for z in ls]);key=h(SYS+"\0"+st)
            req[key]=dict(system=SYS,user=st);ass[q][arm]=key
            if key!=original[q][arm]:amended[q+"/"+arm]=[original[q][arm],key]
        prev[q].update({a:[{k:v for k,v in z.items() if k!="text"} for z in ls] for a,ls in slots[q].items()})
    active={v for a in ass.values() for v in a.values()};missing={k:req[k] for k in active-set(lastinputs)}
    assert all(v=={"system":SYS,"user":v["user"]} for v in missing.values())
    save(P/"effective-strings.json.gz",slots);save(D/"effective-retrieval.json.gz",prev);save(D/"effective-actor-assignment.json.gz",ass)
    save(P/"prefix-requests.json.gz",missing)
    save(D/"prefix-input-seal.json",dict(input=sha(D/"actor-input-seal.json"),audit=sha(D/"blind-audit.json"),questions=sha(P/"reader-questions.json"),
          requests=sha(P/"prefix-requests.json.gz"),assignment=sha(D/"effective-actor-assignment.json.gz"),private_slots=sha(P/"effective-strings.json.gz"),
          public_receipts=sha(D/"effective-retrieval.json.gz"),code=sha(Path(__file__)),max_tokens=80,amended=amended,unique_extra=len(missing),unique_active=len(active),
          changed_early=physical_prefix,changed_retro=retro))
    print("physical prefix",physical_prefix,"retro",retro,"extra unique",len(missing),"effective",len(active))
def finish():
    records={}
    for phase in ("actor","prefix"):
        sig=read(D/(phase+"-forecast-seal.json"));file=P/(phase+"-outputs.json.gz");assert sha(file)==sig["raw"] and sig["failed"]==0
        for k,v in read(file).items():assert k not in records;records[k]=v
    assigned=read(D/"effective-actor-assignment.json.gz");relevant={v for a in assigned.values() for v in a.values()};actual={k:records[k] for k in relevant}
    assert len(assigned)==40 and all(len(a)==4 for a in assigned.values())
    save(P/"effective-actor-outputs.json.gz",actual)
    save(D/"effective-actor-forecast-seal.json",dict(actor=sha(D/"actor-forecast-seal.json"),prefix=sha(D/"prefix-forecast-seal.json"),
        assignment=sha(D/"effective-actor-assignment.json.gz"),raw=sha(P/"effective-actor-outputs.json.gz"),active=len(actual),physical=len(records)))
if __name__=="__main__":
    import sys
    (finish if sys.argv[1:]==["finish"] else prepare)()
