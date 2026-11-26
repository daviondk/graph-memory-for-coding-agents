"""Independently implement a bonus for every supported candidate, with exact dyadic and binary64 checks."""
from fractions import Fraction
from paths_a import *

def bonus_winner(order,scores,marked,t):
    return max(order,key=lambda i:(scores[i]+(t if i in marked else 0),i in marked))

def compare(folder,threshold):
    ranks=get(folder/"orders.json.gz");cat=get(folder/"catalog-receipts.json.gz");rows={}
    for q,r in ranks.items():
        base=cat[q]["tie"];marked=set(r["edges"]);scores={int(k):v for k,v in r["scores"].items()}
        a,b=r["dense"],r["linked_dense"];gap=scores[a]-scores[b]
        selected=r["adaptive"] if folder==D else (b if gap<=threshold else a)
        fp=bonus_winner(base,scores,marked,threshold)
        exact=bonus_winner(base,{i:Fraction.from_float(v) for i,v in scores.items()},marked,Fraction.from_float(threshold))
        assert fp==exact==selected,(folder.name,q,selected,fp,exact)
        rows[q]=[selected,fp,exact,int(a!=b and gap==threshold)]
    return rows

def main():
    check();threshold=get(D/"threshold-seal.json")["primary"]
    all_={name:compare(folder,threshold) for name,folder in [("original_fit",SEM),("confirmation",D)]}
    put(D/"bonus-audit.json.gz",all_)
    summary={name:dict(n=len(rec),all_same=sum(r[0]==r[1]==r[2] for r in rec.values()),boundary_ties=sum(r[3] for r in rec.values())) for name,rec in all_.items()}
    put(D/"bonus-results.json",dict(summary=summary,threshold=threshold,rows=sha(D/"bonus-audit.json.gz"),
        training_source=sha(SEM/"orders.json.gz"),confirmation_source=sha(D/"orders.json.gz")))
    print(summary)
if __name__=="__main__":main()
