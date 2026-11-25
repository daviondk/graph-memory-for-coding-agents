"""CPU realization of the same native residual and matched-zero forward, from all canonical ranks."""
from pathlib import Path
from collections import defaultdict
import torch,numpy as np,time,sys
from setup_graph import ROOT,TR,RUN,pilot,load,put
sys.path.insert(0,str(ROOT/'cpu_fallback'))
from read import ranked_batch
from fit_graph import model_cfg,build_model_from_config,features,tensorize_provenance_ranking_task
from infer_graph import load_rgcn_checkpoint
from vectors import database
from forecasts import Lookup
from data import streams,split,graphfiles
def main():
    torch.set_num_threads(8);torch.manual_seed(13);start=time.monotonic();ck=load(ROOT/'checkpoint.json')
    assert ck['sha']==pilot.sha(RUN/'best.pt')
    plan=load(ROOT/'prediction-plan.json');assert all(pilot.sha(ROOT/f)==w for f,w in plan['files'].items())
    p=load_rgcn_checkpoint(RUN/'best.pt',map_location='cpu');m=build_model_from_config(p.model_config);m.load_state_dict(p.payload['model_state_dict']);m.eval();zero=build_model_from_config(model_cfg).eval()
    hashes={};joint=nodes=standalone_all=standalone_first=0;lookup=Lookup(database(),'ft');ts=graphfiles();pending=[];results={'rgcn':[],'seed':[]};times=[]
    for t,rs,_ in streams('test'):
        n=len(rs[0].graph.nodes)+1;f=np.empty((len(rs)*n,768),dtype='<f4');provider,end=features(rs,lookup,f,0);assert len(f)==end
        for r in rs:
            v=tensorize_provenance_ranking_task(r,model_config=model_cfg,text_embedding_provider=provider,seed_signal_provider=provider)
            pending.append((r,v,t))
            if len(pending)==64:ranked_batch(pending,m,zero,results,times);pending=[]
    ranked_batch(pending,m,zero,results,times)
    sids={r['q'] for r in split('test')};assert all({a['q'] for a in aa}==sids for aa in results.values())
    for name,rows in results.items():
        by=defaultdict(list)
        for r in rows:by[int(ts[r['t']][0].name.split('-',1)[0])].append(r)
        for i,group in sorted(by.items()):
            if name=='seed':
                prev={r['q']:[v['node_id'] for v in r['rr']] for r in load(TR/f'forecasts-main-{i}.json.gz')}
                for r in group:
                    order=[v['node_id'] for v in r['rr']];old=prev[r['q']];assert set(order)==set(old)
                    nodes+=len(order);joint+=1;standalone_first+=old[0]==order[0];standalone_all+=order==old
            fn=f'forecasts-{name}-{i}.json.gz';put(ROOT/fn,group);hashes[fn]=pilot.sha(ROOT/fn)
    put(ROOT/'forecast-seal.json',dict(plan=pilot.sha(ROOT/'prediction-plan.json'),source=pilot.sha(ROOT/'full_cpu_read.py'),forecasts=hashes,queries=joint,candidate_occurrences=nodes,matched_pools=joint,standalone_dense_complete_order_equal=standalone_all,standalone_dense_top1_equal=standalone_first,seconds_total=time.monotonic()-start,paired_cpu_forward_seconds=sum(times),device='cpu'))
if __name__=='__main__':main()

