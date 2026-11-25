"""CPU integration test of the actual native inference and metric code on dev only."""
from pathlib import Path
import tempfile,torch,numpy as np
from data import streams,pilot,load,put,ROOT,RUN,h
from fit_graph import features,model_cfg,build_model_from_config,tensorize_provenance_dev_task,Lookup,database,_predict_provenance_dev_from_batches,evaluate_results,EvidenceEvaluationRequest
from infer_graph import build_evidence_dataloader,move_training_batch,split_batch_node_scores
def run():
    torch.set_num_threads(3);torch.manual_seed(13);c=database();lookup=Lookup(c,'ft')
    dev={r['q']:r for r in load(ROOT/'dev500-pu-dense-ranks.json.gz')}
    m=build_model_from_config(model_cfg).eval()
    results=[];skipped=0
    for t,rs,labs in streams('dev'):
        try:
            n=len(rs[0].graph.nodes)+1
            data=np.empty((len(rs)*n,768),dtype='<f4');prov,nwritten=features(rs,lookup,data,0)
        except KeyError:
            skipped+=1;continue
        assert nwritten==len(data)
        tasks=[tensorize_provenance_dev_task(r,labs[r.task_id],model_config=model_cfg,text_embedding_provider=prov,seed_signal_provider=prov) for r in rs]
        batches=build_evidence_dataloader(tasks,per_device_graph_batch_size=128,shuffle=False,random_seed=13)
        for b in batches:
            with torch.inference_mode():v=m(b)
            assert torch.equal(v,b.sample_node_features[:,0])
        ranks,loss=_predict_provenance_dev_from_batches(model=m,requests=rs,batches=batches,device=torch.device('cpu'))
        vals=evaluate_results(EvidenceEvaluationRequest(predictions=tuple(ranks),labels=tuple(labs[r.task_id] for r in rs),graphs=()))[0]
        for r,rk in zip(rs,ranks,strict=True):
            refs=dev[r.task_id]['rr'];results.append(dict(q=r.task_id,t=t,nodes=n,candidates=len(refs),native_returned=len(rk.ranked_nodes),direct_top1=rk.ranked_nodes[0].node_id==refs[0]['node_id'],dev_loss_batch=loss,
                                                        recall5_batch=vals.recall_at_5))
        if len(results)>=8:break
    assert len(results)>=8 and all(v['native_returned']==min(v['candidates'],10) or v['native_returned']==v['candidates'] for v in results)
    put(ROOT/'native-smoke.json',dict(results=results,graphs_skipped_while_features_pending=skipped,zero_initial_logit_exact=True,device='cpu',purpose='Small dev-only pipeline check; information from these dev queries never selects hyperparameters'))
if __name__=='__main__':run()

