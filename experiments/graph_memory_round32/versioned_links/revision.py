"""Inspect real within-title source revisions and contrast with an explicitly constructed update."""
from collections import Counter
from dataclasses import replace
from hashlib import sha256
from replay import ROOT,project,tie,lex,entries,select,update,put,sha,Tokenizer,E5


def main():
    rows=project();seen={};changed=[];counts=Counter(); synthetic=[]
    for r in rows:
        old=seen.get(r.title)
        if old and old.revision!=r.revision:
            before,after=lex(old.snippet),lex(r.snippet)
            a,b=entries(r,before),entries(r,after)
            rec={"q":r.qid,"title_hash":tie(r.title).hex(),"old_rev":old.revision,"new_rev":r.revision,
                 "different_snippet":old.snippet!=r.snippet,"different_tokens":before!=after,
                 "different_windows":a!=b,"different_choice":select(r,a)!=select(r,b)}
            changed.append(rec)
            counts.update(k for k,v in rec.items() if v is True)
        seen[r.title]=r

    tok=Tokenizer.from_file(str(E5/"tokenizer.json"))
    for r in sorted(rows,key=lambda r:tie("version-sensitivity/"+r.qid))[:128]:
        eligible=[(j,phrase) for j,(phrase,_) in r.addresses.items() if j!=r.gold and phrase]
        j,phrase=min(eligible,key=lambda item:tie(r.qid+"|"+str(item[0])))
        # A controlled new observation naming a hash-selected alternate catalog item.
        short=" ".join(phrase);cost=len(tok.encode(short,add_special_tokens=False).ids);assert cost<=192
        revised=replace(r,revision=sha256(short.encode()).hexdigest(),snippet=short,tokens=cost)
        current=select(r,entries(r,lex(short)))
        row={"q":r.qid,"edited_candidate":j,"before":r.gold,"after":current,"methods":{}}
        for m in ("raw","normalized","memo","bloom","title_only"):
            before,blob,_=update(r,m,None)
            answer,_,miss=update(revised,m,blob if m=="title_only" else None)
            row["methods"][m]=[answer,int(miss)]
            assert before==r.gold and (answer==r.gold if m=="title_only" else answer==current)
        synthetic.append(row)
    put(ROOT/"revision-audit.json",{"real":changed,"counts":dict(counts),"synthetic":synthetic,"synthetic_target_changed":sum(c["before"]!=c["after"] for c in synthetic)})
if __name__=="__main__":
    main()
