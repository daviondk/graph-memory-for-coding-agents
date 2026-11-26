"""Re-run the two stored official580 seed-13 graph checkpoints on CPU only."""
import os
for k in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS","RAYON_NUM_THREADS"):os.environ[k]="1"
import sys,tempfile,gc
from pathlib import Path
ROOT=Path(__file__).resolve().parent;WORK=ROOT.parents[1]
UP=WORK/"graph_memory_round22/native_multiseed/official580"
sys.path.insert(0,str(UP))
import official as run
from official import torch,load,save,sha
DATA=Path("D:/CodexResearch/x20-r33-relative-scratch")
def main():
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    DATA.mkdir(exist_ok=True)
    cp,weight=run.signed_selection(13);pub,private=run.seed_paths(13)
    baseline=load(WORK/"graph_memory_round20/residual_graph/dev500-pu-dense-ranks.json.gz");canonical={r["q"]:{c["node_id"]:j for j,c in enumerate(r["rr"])} for r in baseline}
    assert set(canonical)=={v["q"] for v in load(UP/"split.json.gz")["dev"][:500]}
    for arm in ("full_rgcn","wo_chunk_adjacency"):
        receipt=load(pub/arm/"fit.json");src=private/receipt["attempt"]/"best.pt";assert sha(src)==receipt["checkpoint"] and receipt["weight"]==weight
        ck=run.inf.load_rgcn_checkpoint(src,map_location="cpu");cfg=run.old.model(13,arm,cp);assert cfg==ck.model_config
        net=run.fit.build_model_from_config(cfg);net.load_state_dict(ck.payload["model_state_dict"]);net.eval()
        with tempfile.TemporaryDirectory(dir=DATA) as tmp:
            tasks,requests,labels=run.make_dev(cfg,13,Path(tmp))
            with torch.inference_mode():
                out={}
                for batch in run.inf.build_evidence_dataloader(tasks,per_device_graph_batch_size=128,shuffle=False,random_seed=13):
                    scores=net(run.inf.move_training_batch(batch,"cpu"))
                    for q,ids in run.old.orders(batch,scores).items():
                        if q in canonical:
                            by=canonical[q]
                            assert len(ids)==len(by) and set(ids)==set(by)
                            out[q]=[by[j] for j in ids]
            assert set(out)==set(canonical);save(ROOT/(arm+"-dev500-ranks.json.gz"),out)
            del tasks,requests,labels,batch,scores;gc.collect()
        print(arm,len(out),flush=True)
    save(ROOT/"rgcn-dev-seal.json",{"ranks":{a:sha(ROOT/(a+"-dev500-ranks.json.gz")) for a in ("full_rgcn","wo_chunk_adjacency")},"weights":{a:load(pub/a/"fit.json")["checkpoint"] for a in ("full_rgcn","wo_chunk_adjacency")},"code":sha(Path(__file__)),"e5":weight})
if __name__=="__main__":main()
