"""Audit frozen coordinates, allowed source pieces, native prices, and document selection without answer annotations."""
from collections import Counter
from prepare import D,P,R,ARMS,WP,ENCT,h,sha,read,save,Tokenizer,Path
def main():
    lock=read(D/"input-lock.json");assert lock["contexts"]==sha(D/"contexts.json.gz")
    rows=read(D/"contexts.json.gz");v=read(P/"blind-input.json.gz");assert sorted(v)==["docs","qs"]
    original=read(R/"squad-opened.json.gz");choices=read(R/"squad-choices.json.gz")
    ct=Tokenizer.from_file(str(ENCT));ut=Tokenizer.from_file(str(WP));n=lambda t,s:len(t.encode(s,add_special_tokens=False).ids)
    counts=Counter();prices=[];native_ok=0;real=Counter();ucd=[]
    for q,row in rows.items():
        title,query=v["qs"][q];text=v["docs"][title];a=choices[q]
        assert title==a["t"] and row["base"]==[[l,r,l] for _,l,r in a["base"]]
        x=row["arms"];native=[];uncased=[]
        for k,arm in x.items():
            p=row["base"]+arm["extra"]
            wire="\n".join(f"[0:{c}] "+text[l:r] for l,r,c in p)
            assert h(wire)==arm["wire_sha"] and n(ct,wire)==arm["native_wire"]
            if k=="base":continue
            source=original[q]["arms"][k]
            for l,r,z in arm["extra"]:
                matched=[a for a in source if a[4]==z and a[1]<=l<r<=a[2] and ((a[5]=="L" and r==a[2]) or (a[5]=="R" and l==a[1]))]
                assert len(matched)==1
            extra="\n".join(f"[0:{c}] "+text[l:r] for l,r,c in arm["extra"])
            assert n(ct,extra)==arm["native_extra"]<=256 and n(ut,extra)==arm["unc_extra"]<=256
            native.append(arm["native_wire"]);uncased.append(arm["unc_extra"]);real[k]+=len(arm["extra"])
        assert len(set(native))==1;native_ok+=1;ucd.append(max(uncased)-min(uncased))
        prices.append(x["both"]["native_extra"]);counts[title]+=1
    assert set(counts.values())=={12} and len(counts)==48
    save(D/"input-audit.json",dict(queries=native_ok,articles=len(counts),per_article=12,checked_wire_strings=native_ok*4,
         common_native_extra_min=min(prices),common_native_extra_mean=sum(prices)/len(prices),common_native_extra_max=max(prices),
         empty_extensions=prices.count(0),unmatched_uncased_queries=sum(z!=0 for z in ucd),largest_uncased_difference=max(ucd),
         actual_pieces=real,input_seal=sha(D/"input-lock.json"),audit=sha(Path(__file__))))
    print(native_ok,len(counts),real)
if __name__=="__main__":main()
