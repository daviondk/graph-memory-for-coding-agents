"""Select no labels: inventory complete graph/candidate features per original train trajectory."""
from setup_graph import ROOT,RUN,TR,TRAINED,load,put,pilot,h
from data import graphfiles,split
from vectors import database
import hashlib
def main():
    c=database();observed={k for k, in c.execute("select k from vectors where prec='ft'")};base={k for k, in c.execute("select k from vectors where prec='base'")}
    gs=graphfiles();out=[];qs={}
    for r in split('train'):qs.setdefault(r['t'],set()).add(r['q'])
    for t,ids in sorted(qs.items()):
        p,w=gs[t];rec=load(p);keys={h('passage: '+v['text']) for v in rec['g']['nodes']};q={h('query: '+v) for _,v in rec['q']};keys|=q
        pu={h('passage: '+v['text']) for v in rec['g']['nodes'] if v['kind'] in {'content.tool_output','content.tool_argument'}}|q
        out.append(dict(t=t,n=len(ids),graph_keys=len(keys),pu_keys=len(pu),missing_ft=len(keys-observed),missing_base=len(pu-base),ft_complete=not bool(keys-observed)))
    put(ROOT/'outage-train-availability.json.gz',out)
    relevant=[r for r in out if r['ft_complete']];summary=dict(total_trajectories=len(out),total_queries=sum(x['n'] for x in out),ft_complete_trajectories=len(relevant),ft_complete_queries=sum(x['n'] for x in relevant),both_complete_queries=sum(x['n'] for x in relevant if x['missing_base']==0),mining_costs=sorted([v['missing_base'] for v in relevant])[::max(1,len(relevant)//10)])
    put(ROOT/'outage-coverage.json',summary);print(summary)
if __name__=='__main__':main()

