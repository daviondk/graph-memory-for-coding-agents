"""Invert five-seed rounded FS mean/sample-SD under the stated 2000-query test."""
from decimal import Decimal
from itertools import combinations_with_replacement
import math
from prepare import ROOT,put
def solve(mu,sd):
    # Counts h imply mean% = sum(h)/100 and sample-SD% = sqrt((5*sum(h^2)-sum(h)^2)/20)/20.
    N=2000;n=5;mu=Decimal(mu);sd=Decimal(sd);tol=Decimal('.005')
    S=int(mu*100);assert Decimal(S)/100==mu
    # Standardized maximum of an individual observation at fixed sample SD <= (n-1)/sqrt(n).
    radius=(n-1)/math.sqrt(n)*float(sd+tol)*N/100
    lo=math.floor(S/n-radius)-1;hi=math.ceil(S/n+radius)+1
    low2=(sd-tol)**2*8000;high2=(sd+tol)**2*8000
    ncfg=0;values=set()
    for a,b,c,d in combinations_with_replacement(range(lo,hi+1),4):
        e=S-a-b-c-d
        if e<d or e>hi:continue
        D=5*(a*a+b*b+c*c+d*d+e*e)-S*S
        if low2<=D<=high2:
            ncfg+=1;values.update((a,b,c,d,e))
    assert values
    return dict(mean_percent=str(mu),sample_sd_percent=str(sd),n_seeds=n,n_queries=N,sum_hits_across_seeds=S,unordered_feasible_count=ncfg,
                min_possible_hits=min(values),max_possible_hits=max(values),min_possible_percent=min(values)/20,max_possible_percent=max(values)/20,possible_hits=sorted(values))
def run():
    put(ROOT/'published-seed-bounds.json',{k:solve(m,s) for k,m,s in [('pu_dense_ft','72.78','0.64'),('residual_rgcn','77.33','0.53')]})
if __name__=='__main__':run()
