"""Validate independent semantic judgements against the visible source and describe the deliberately balanced audit sample."""
from base31 import D,P,h,read,save,sha,Path
from collections import Counter
def main():
    packet=read(P/"review-packet.json");key=read(P/"review-map.json");rat=[read(P/("reviewer-"+n+".json")) for n in ("A","B")]
    assert all(set(j)==set(key) for j in rat);out=[];mat=Counter()
    for r in packet:
        id=r["id"];a,b=(j[id] for j in rat)
        for z in (a,b):
            quote=z["quote"]
            assert z["label"] in ("S","P","N") and (z["label"]=="N" or bool(quote.strip())),id
            assert quote in r["excerpt"],(id,z["label"])
        bucket=key[id]["bucket"];mat[bucket+"/"+a["label"]+"/"+b["label"]]+=1
        out.append(dict(id=id,bucket=bucket,case=key[id]["case"],source=key[id]["evidence_source"],
            start=key[id]["evidence_start"],end=key[id]["evidence_end"],a=a["label"],b=b["label"],
            quoteA_hash=h(a["quote"]),quoteB_hash=h(b["quote"])))
    same=sum(z["a"]==z["b"] for z in out);ma=Counter(z["a"] for z in out);mb=Counter(z["b"] for z in out)
    p0=same/len(out);pe=sum(ma[i]*mb[i] for i in "SPN")/(len(out)**2)
    save(D/"semantic-audit.json",dict(score=sha(D/"score.json"),packet=sha(P/"review-packet.json"),reviewer_A=sha(P/"reviewer-A.json"),
            reviewer_B=sha(P/"reviewer-B.json"),code=sha(Path(__file__)),n=len(out),agreement=same,kappa=(p0-pe)/(1-pe) if pe<1 else None,
            confusion=mat,graded=out))
if __name__=="__main__":main()
