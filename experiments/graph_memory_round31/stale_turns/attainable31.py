"""Diagnostic source-local oracles. Check whether a true literal can fit in an exactly cost-matched candidate frame."""
from base31 import D,P,sha,h,read,save,DATA,Path,data
from predict31 import source,profiles,Tokenizer,QWT,WIDTH
from collections import Counter,defaultdict
import bisect
def main():
    gold=read(D/"gold-spans.json.gz");pred=read(D/"forecast.json.gz");access=read(D/"access.json.gz")
    qs=data();split=read(D/"case-split.json");tok=Tokenizer.from_file(str(QWT));summary=defaultdict(Counter);allrows=[]
    for c,questions in qs.items():
        hist={s["id"]:s for s in read(DATA/"history"/(c+".json.gz"))["sources"]};dicts={};cache={};part=split[c]
        for side in ("old","new"):
            z=gold[c+"/"+side];sk=z["source"];dicts[sk]=source(hist[sk],tok)
        for q in questions:
            for name,k in access[q].items():
                frames={z["source"]:z for z in pred[k]["turn_pair"]};flags={}
                for side in ("old","new"):
                    z=gold[c+"/"+side];sk=z["source"];s=dicts[sk]
                    options={a:False for a in ("turn","grid","gold_span")}
                    if sk in frames:
                        cap=frames[sk]["native"];ck=(side,cap)
                        if ck in cache:options=cache[ck]
                        else:
                            n=len(s["off"]);last=max(0,n-WIDTH);ends=[b for a,b in s["off"]]
                            fam={"turn":set(s["starts"]),"grid":set(s["grid"]),"gold_span":set()}
                            for loc in z["locations"]:
                                a,b=loc["span"];first=bisect.bisect_right(ends,a);after=bisect.bisect_left(ends,b)+1
                                fam["gold_span"].update(min(last,max(0,start)) for start in (first,after-WIDTH,(first+after-WIDTH)//2))
                            starts=set.union(*fam.values())
                            possible=set()
                            for j in starts:
                                lo=s["off"][j][0];hi=s["off"][min(n,j+WIDTH)-1][1]
                                occ=[a["span"] for a in z["locations"] if lo<=a["span"][0] and hi>=a["span"][1]]
                                if not occ:continue
                                p=profiles(s,j,tok,False)
                                if cap not in p:p=profiles(s,j,tok,True)
                                if cap in p and any(b<=p[cap][0] for a,b in occ):possible.add(j)
                            options={m:bool(pts&possible) for m,pts in fam.items()};cache[ck]=options
                    flags[side]=options
                result={v:flags["old"][v] and flags["new"][v] for v in ("turn","grid","gold_span")}
                item=dict(case=c,q=q,scope=name,split=part,both=result,side=flags);allrows.append(item)
                for p in (part,"all"):
                    dest=summary[p+"/"+name];dest["n"]+=1
                    for m,ok in result.items():
                        dest["both_"+m]+=ok;dest["old_"+m]+=flags["old"][m];dest["new_"+m]+=flags["new"][m]
    save(D/"attainable-rows.json.gz",allrows);save(D/"attainable.json",dict(score=sha(D/"score.json"),code=sha(Path(__file__)),
              rows=sha(D/"attainable-rows.json.gz"),summary=summary))
if __name__=="__main__":main()
