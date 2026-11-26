"""Materialize six native metrics for frozen R35 ranks and join all four policies on exact query/seed."""
from pathlib import Path
import gzip,hashlib,json,sys
from shutil import copyfile
import numpy as np
D=Path(__file__).resolve().parent;W=D.parents[1];CP=D.parent/"native_checkpoint3";R35=W/"graph_memory_round35";S=R35/"calibration_scale";T=R35/"calibration_transfer"
B=W/"graph_memory_round33/budget_loss";sys.path.insert(0,str(B));from data import nm,sources
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,x):
    b=(json.dumps(x,sort_keys=True,separators=(",",":"))+"\n").encode();p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def main():
    if (D/"manifest.json").exists():raise RuntimeError("Snapshot already frozen")
    assert sha(CP/"manifest.json")=="a6dacff456dcb7f3afc2c190c8f04cc82ec9b00010ed309033fb8d0cd440e0f2"
    assert all(sha(CP/n)==v for n,v in read(CP/"manifest.json").items())
    seedlist=[13,17,29];signed=read(T/"forecast-seal.json")["orders"];orig=read(S/"test-orders.json.gz")
    assert sha(S/"test-orders.json.gz")==read(S/"test-seal.json")["orders"]
    prior=read(T/"outcomes.json.gz");assert sha(T/"outcomes.json.gz")==read(T/"measure-seal.json")["outcomes"]
    truths=read(nm.OFF/"gold-spans.json.gz");native={s:read(CP/f"outcomes-{s}.json.gz") for s in seedlist};rows={s:{} for s in seedlist}
    sigs={}
    for i,p in enumerate(sources("test")):
        rank=T/f"orders-{i}.json.gz";assert sha(rank)==signed[rank.name];scores=read(rank);sigs[rank.name]=sha(rank)
        for rec in read(p):
            q=rec["q"];t=rec["t"];pool=[nm.pilot.RankedNodeRecord.model_validate(r) for r in rec["rr"]]
            spans=tuple(nm.pilot.SourceSpan.model_validate(r) for r in truths[q])
            for s in seedlist:
                seq=orig[q]["oof_3894"] if s==13 else scores[q][str(s)]["oof_3894"];assert sorted(seq)==list(range(len(pool)))
                z=tuple(pool[j] for j in seq);bs=[nm.pilot.span_metrics_under_token_budget(z,spans,b) for b in (512,1024,2048)]
                val=[float(bs[2].full_support),*[float(b.coverage) for b in bs],float(nm.span_metrics_at(z,spans,5).coverage),float(nm.span_mrr(z,spans))]
                assert prior[q]["t"]==native[s][q][0]==t
                pub=prior[q]["seeds"][str(s)]["oof_3894"];r33=prior[q]["seeds"][str(s)]["original_R33"]
                assert np.allclose([val[0],val[5],val[3]],[pub[0],pub[3],pub[4]],atol=1e-12,rtol=0)
                prev=native[s][q]
                assert np.allclose([prev[1][0],prev[1][5],prev[1][3]],[r33[0],r33[3],r33[4]],atol=1e-12,rtol=0)
                rows[s][q]=[t,val,*prev[1:]]
    for s in seedlist:
        assert len(rows[s])==2000
        put(D/f"four-arms-{s}.json.gz",rows[s]);copyfile(CP/f"seed-{s}.json",D/f"checkpoint-audit-{s}.json")
    put(D/"inputs.json",{"plan":sha(D/"PROTOCOL_RU.md"),"program":sha(D/"measure.py"),"prior_native":sha(CP/"manifest.json"),
         "r35_scale":sha(S/"manifest.json"),"r35_transfer":sha(T/"manifest.json"),"rank_13":sha(S/"test-orders.json.gz"),
         "ranks_17_29":sigs,"original_r35_metrics":sha(T/"outcomes.json.gz"),"gold":sha(nm.OFF/"gold-spans.json.gz"),
         "rows":{s:sha(D/f"four-arms-{s}.json.gz") for s in seedlist},"metrics":["full_support_2048","coverage_512","coverage_1024","coverage_2048","recall_5","mrr"],
         "models":["R35_oof_3894","R33_cost_worst","full_rgcn","wo_chunk_adjacency"],"per_seed":2000})
    print("Recomputed six native metrics for 6000 R35 orderings",flush=True)
if __name__=="__main__":main()
