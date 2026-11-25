"""Check if literal address-only records change the chosen full-message budgets or source spans."""
from pathlib import Path
from collections import Counter
import contexts28 as c
def main():
    view=c.read(Path("D:/CodexResearch/x20-r26-squad-qa/blind-input.json.gz"))
    contexts=c.read(c.D/"contexts.json.gz");ini=c.read(c.R25/"squad-choices.json.gz");old=c.read(c.R25/"squad-opened.json.gz")
    index=c.read(c.D/"sentence-index.json.gz");ut=c.Tokenizer.from_file(str(c.WP));ct=c.Tokenizer.from_file(str(c.ENCT))
    original=c.convert;counts=Counter();changed={}
    def literal(ops,src):
        groups=[];a=None;delivered=None
        for atom in ops:
            if atom[0]=="h":a=atom[1];delivered=[a,a,a];groups.append(delivered)
            if atom[0]=="s":delivered[:]=[atom[1],atom[2],a]
        assert c.wire(src,groups)[0]=="".join(c.txt(p,src) for p in ops)
        counts["profiles_checked"]+=1
        if original(ops,src) is None:counts["address_only_profiles"]+=1
        return groups
    c.convert=literal
    for q,r in contexts.items():
        new=c.make(q,view,ini,old,index,c.Memo(ut),c.Memo(ct))
        if new!=r:
            changed[q]=new
    c.save(c.P/"address-only-changed.json.gz",changed)
    c.save(c.D/"address-only-audit.json",dict(n=len(contexts),counts=counts,changed_queries=len(changed),changes=c.sha(c.P/"address-only-changed.json.gz"),
        inputs=c.sha(c.D/"context-seal.json"),code=c.sha(Path(__file__))))
    print(len(changed),dict(counts),flush=True)
if __name__=="__main__":main()
