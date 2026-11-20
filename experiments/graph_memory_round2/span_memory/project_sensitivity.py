"""Describe between-project heterogeneity for the registration's primary comparison."""
import itertools
import numpy as np
from run import read,save
def main():
    groups=read("results.json")["typed_minus"]["global"]["by_project"]
    scores=np.array(list(groups.values()));d,n=scores.T
    totals=(d.sum()-d)/(n.sum()-n);mu=d/n
    rng=np.random.default_rng(261118)
    bs=rng.integers(len(n),size=(10000,len(n)));ci=np.quantile(mu[bs].mean(axis=1),[.025,.975]).tolist()
    signs=np.asarray(list(itertools.product((-1,1),repeat=len(n))),dtype=np.int8)
    p=float(np.mean(np.abs(signs@d)>=abs(d.sum())))
    save("project_sensitivity.json",{"n":len(n),"weighted_leave_one_out_range":[min(totals),max(totals)],"macro":float(mu.mean()),"macro_ci":ci,"cluster_signflip_event_weighted_p":p,"positive":int((d>0).sum()),"negative":int((d<0).sum()),"tie":int((d==0).sum())})
if __name__=="__main__":main()
