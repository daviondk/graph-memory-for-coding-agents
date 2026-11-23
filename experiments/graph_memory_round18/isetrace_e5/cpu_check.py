"""Compare sealed native CUDA rankings with the already archived R17 native CPU reranking."""
from project import ROOT,OFF,load,put,pilot
import numpy as np
def check():
    f=OFF.parents[1]/'graph_memory_round17/isetrace/dense/ranked.json.gz'
    cpu={r['query']:r['ranking'] for r in load(f)}
    seal=load(ROOT/'forecast-seal.json')
    top1=top5=identical=0;errs=[];rows=[]
    for n,h in seal['forecasts'].items():
        assert pilot.sha(ROOT/n)==h
        if not n.startswith('forecasts-main-'):continue
        for rec in load(ROOT/n):
            q=rec['q']
            if q not in cpu:continue
            a=cpu[q];b=rec['rr'];ai=[r['node_id'] for r in a];bi=[r['node_id'] for r in b]
            assert set(ai)==set(bi)
            av={r['node_id']:r['score'] for r in a}
            err=[abs(av[r['node_id']]-r['score']) for r in b];errs+=err
            top1+=ai[:1]==bi[:1];top5+=ai[:5]==bi[:5];identical+=ai==bi
            rows.append(dict(q=q,t=rec['t'],n=len(ai),equal_top1=ai[:1]==bi[:1],equal_top5=ai[:5]==bi[:5],equal_order=ai==bi,max_score_error=max(err)))
    put(ROOT/'cpu-check.json',dict(cpu_file_sha256=pilot.sha(f),cpu_query_total=len(cpu),overlap=len(rows),candidates=len(errs),
             equal_top1=top1,equal_top5_in_order=top5,equal_complete_ranking=identical,
             max_abs_score_difference=max(errs,default=None),mean_abs_score_difference=float(np.mean(errs)) if errs else None,rows=rows))
if __name__=='__main__':check()
