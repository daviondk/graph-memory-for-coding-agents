"""Reconstruct binary64 from the original causal model features; verify every stored Q32 integer."""
from array import array
from hashlib import sha256
import gzip,json,os,sys
from pathlib import Path
for k in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"): os.environ[k]="1"
import numpy as np
D=Path(__file__).resolve().parent
S=D.parents[1]/"learned_stream";W=D.parents[2]
R=W/"graph_memory_round41/causal_budget"
sys.path.insert(0,str(R))
import forecast_packets as f

def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return sha256(p.read_bytes()).hexdigest()

def main():
    assert sys.byteorder=="little" and array("d").itemsize==8
    src=Path("D:/CodexResearch/x20-r33-budget-loss/test.json.gz")
    assert sha(src)==read(W/"graph_memory_round33/budget_loss/test-input.json")["features"]
    original={r["q"]:r for r in read(src)}
    model=read(W/"graph_memory_round39/global_packet/models.json")["models"]["graph"]
    signed=read(R/"manifest.json")["files"]
    receipt={}
    for seed in (13,17,29,37,41):
        staged={}
        ranks=read(W/"graph_memory_round20/factor_reader/hash64-weights.json")["rank"] if seed==13 else read(W/f"graph_memory_round21/five_seed/seed-{seed}/calibration.json")["rank"]
        for sh in range(8):
            p=R/f"state-{sh}.json.gz";assert sha(p)==signed[p.name]
            other={} if seed==13 else {r["q"]:r["dense"] for r in read(W/f"graph_memory_round21/five_seed/seed-{seed}/picks-{sh}.json.gz")}
            rows=[];mat=[]
            for q,tr,pct,at,visible,graph,pilot in read(p):
                ids=np.array(visible,dtype=int);n=len(ids);ix={v:i for i,v in enumerate(ids)}
                dense=np.arange(n) if seed==13 else np.asarray([ix[j] for j in other[q] if j in ix])
                features=np.asarray(original[q]["x"])[ids].copy()
                offset=np.empty(n);offset[dense]=f.packet.base.linear(ranks,f.packet.base.rankx(n))
                features[dense,0]=np.log1p(np.arange(1,n+1))
                x,order=f.packet.feature(features,np.asarray(graph),offset)
                rows.append((sha256(q.encode()).hexdigest(),pct,n,order));mat.append(x)
            v=np.logaddexp(0,f.packet.portable(model,np.vstack(mat)[:,model["cols"]]))
            start=0
            for q,pct,n,order in rows:
                staged[q,pct]=v[start:start+n][order]
                start+=n
            assert start==len(v)
        prior=S/f"input-{seed}.json.gz";inp=read(prior);buf=array("d")
        for q in sorted(inp):
            for pct,at,ids,u,pub in inp[q]["states"]:
                v=staged[q,pct];assert np.array_equal(np.rint(v*2**32).astype(np.int64),u)
                assert np.isfinite(v).all() and np.all(v>0)
                buf.frombytes(v.astype("<f8",copy=False).tobytes())
        out=D/f"weights-{seed}.f64.gz";out.write_bytes(gzip.compress(buf.tobytes(),compresslevel=6,mtime=0))
        receipt[seed]=dict(binary=sha(out),source=sha(prior),count=len(buf))
        print("floating weights",seed,len(buf),flush=True)
    (D/"inputs.json").write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n","utf8",newline="\n")
if __name__=="__main__":main()
