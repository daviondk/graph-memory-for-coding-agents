"""Exact rate-matched null for the selective policy given fixed potential outcomes.

The fixed single matched random seed in SELECTIVE_READ_RU.md remains the registered primary test.
This sensitivity was defined before scoring B/empty. Strata affect only the quota of random
reads. For each stratum the all-subsets distribution follows from multivariate hypergeometric
probabilities for helpful, neutral and harmful reads. Convolve independent strata.
"""
import itertools,math
from collections import Counter,defaultdict
from infer import read,save

def distribution(n, count, k):
    plus=count[1];minus=count[-1];neutral=n-plus-minus;result=Counter()
    for x in range(min(plus,k)+1):
        for y in range(min(minus,k-x)+1):
            z=k-x-y
            if z<=neutral: result[x-y]+=math.comb(plus,x)*math.comb(minus,y)*math.comb(neutral,z)
    assert sum(result.values())==math.comb(n,k)
    return result
def merge(a,b):
    c=Counter()
    for k,n in a.items():
        for t,m in b.items():c[k+t]+=m*n
    return c

def quant(dist,q):
    m=sum(dist.values());c=0
    for x,n in sorted(dist.items()):
        c+=n
        if c/m>=q:return x

def main():
    plan=read("selective_choices.json");results={}
    for key in ("A","B"):
        group=defaultdict(list)
        data=read(key+"_selective_items.json.gz")
        for item in data:group[item["panel"]].append(item)
        empty=sum(x["methods"]["empty"]["em"] for x in data)
        curr=sum(x["methods"]["use"]["em"] for x in data)
        pooled=Counter({empty:1})
        for panel,rows in group.items():
            effects=Counter(x["methods"]["graph"]["em"]-x["methods"]["empty"]["em"] for x in rows)
            k=sum(plan[key][x["id"]]["use"] for x in rows)
            pooled=merge(pooled,distribution(len(rows),effects,k))
        m=sum(pooled.values())
        results[key]={"quota_matched_combinations":str(m),"observed_policy_em_count":curr,"random_expected_em_count":sum(x*v for x,v in pooled.items())/m,
        "chance_random_equals_or_beats_policy":sum(v for x,v in pooled.items() if x>=curr)/m,"random_central_95":[quant(pooled,.025),quant(pooled,.975)],"observed_n":len(data)}
    save("selective_exact_null.json",results)
if __name__=="__main__":main()

