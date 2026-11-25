"""Physically materialize each early prefix before encoding. No evaluator, oracle or actor output is read."""
from retrieve29 import chunks,encode,choose,make_slots,Tokenizer,QWT,E5,e5_session,words
from setup29 import D,P,h,sha,read,save
def main():
    sig=read(D/"input-seal.json");lock=read(D/"retrieval-seal.json")
    old=read(P/"retrieval-strings.json.gz");saved=read(D/"retrieval.json.gz")
    qs=read(P/"reader-questions.json");hs=read(P/"reader-histories.json.gz")
    assert sha(P/"retrieval-strings.json.gz")==lock["private"] and sha(P/"reader-questions.json")==sig["questions"]
    assert all(set(q)=={"query","ask","available_until","asof","case"} for q in qs.values())
    assert all(set(s)=={"id","sequence","time","turns"} for hist in hs.values() for s in hist)
    tok=Tokenizer.from_file(str(QWT));et=Tokenizer.from_file(str(E5/"tokenizer.json"));engine=e5_session()
    proofs={};different={};boundary_violations=[];slot_mismatch=0
    for q,r in qs.items():
        slot_mismatch+=len({tuple(i["n"] for i in slots) for slots in old[q].values()})!=1
        cutoff=r["available_until"]
        for arm,slots in saved[q].items():
            scope=r["asof"] if r["asof"] is not None and arm in {"T","G"} else cutoff
            if any(s["seq"]>scope for s in slots):boundary_violations.append([q,arm])
        if cutoff>=len(hs[r["case"]])-1:continue
        candidate_hist=[s for s in hs[r["case"]] if s["sequence"]<=cutoff]
        rows=chunks(candidate_hist,tok);em=encode(["query: "+r["query"]]+["passage: "+z["chunk"] for z in rows],et,engine)
        picks=choose(r,rows,[words(z["chunk"]) for z in rows],em[1:],em[0])
        slots=make_slots(picks,rows,tok);new={a:[[s["source"],s["origin"],s["end"],h(s["text"])] for s in z] for a,z in slots.items()}
        before={a:[[s["source"],s["origin"],s["end"],h(s["text"])] for s in z] for a,z in old[q].items()}
        bm=[[rows[i]["source"],rows[i]["start"],rows[i]["end"]] for i in picks["B"]];oldbm=[[s["source"],s["origin"],s["end"]] for s in saved[q]["B"]]
        proofs[q]={"n_sessions":len(candidate_hist),"n_chunks":len(rows),"early_only":new,"original":before,"bm_equal":bm==oldbm,
                   "all_addresses_identical":all([x[:2] for x in new[a]]==[x[:2] for x in before[a]] for a in new),
                   "all_inputs_identical":new==before}
        if slots!=old[q]:different[q]=slots
    save(P/"early-hardened-differences.json.gz",different)
    save(D/"blind-audit.json",dict(input_seal=sha(D/"input-seal.json"),retrieval_seal=sha(D/"retrieval-seal.json"),
           code=sha(__import__("pathlib").Path(__file__)),cases=proofs,ordinary_fields_checked=True,slot_mismatches=slot_mismatch,
           late_addresses=boundary_violations,hardened_changed=len(different),private_changes=sha(P/"early-hardened-differences.json.gz")))
    print("early",len(proofs),"changed",len(different),"future",len(boundary_violations),"slot-mismatch",slot_mismatch)
if __name__=="__main__":main()
