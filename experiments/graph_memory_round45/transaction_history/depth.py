from inputs import *
def main():
    p=read(OUT/"forecasts.json.gz");o=read(OUT/"outcomes.json.gz");counts=defaultdict(lambda:defaultdict(Counter));cause=defaultdict(set);maxdepth=Counter()
    for k,r in p.items():
        z=o[k]
        for name,ar in r["arms"].items():
            d=dict(zip(ar["all"],ar["depth"],strict=True))
            for t in ("all","read"):
                for i in ar[t]:
                    old,new,w=z["checks"][i];tier=str(min(2,d[i]));maxdepth[name]=max(maxdepth[name],d[i]);c=counts[name][t]
                    c["candidates_depth"+tier]+=1;c["demand_depth"+tier]+=new*w
        a=z["arms"]["local_8192"]["read"];b=z["arms"]["reset_8192"]["read"]
        for metric in ("hit","novel_lines"):
            if a[metric]!=b[metric]:
                for key in ("repo","issue","run"):cause[metric+"_"+key].add(z[key])
                cause[metric+"_edits"].add(k)
    wr("depth-summary.json",dict(counts=counts,maximum_depth=maxdepth,cause={k:len(v) for k,v in cause.items()},forecasts=sha(OUT/"forecasts.json.gz"),grades=sha(OUT/"outcomes.json.gz")))
if __name__=="__main__":main()
