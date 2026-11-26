"""Physically encode both independently charged components of every pending live state."""
import inputs
from transact import Transaction,escrow
from inputs import *
def confirm(n,v):assert n=="input-seal.json" and v==read(OUT/n)
def main():
    inputs.wr=confirm
    frames,views,receipt,starts,ends,bodies=collect();counts=defaultdict(Counter);byrun={}
    for rid,seq in frames.items():
        ws={(m,c):Transaction(m,c) for m in ("charged","range","local") for c in (*CAPS,None)}
        for at,kind,path in seq:
            for (m,c),w in ws.items():
                ok=w.before(at,kind,path,ends.get(rid,{}).get(at));name=label(m,c);s=counts[name]
                if kind in ("gap","barrier","finish"):w.clear()
                elif kind=="read":w.read(path,at,views[rid][str(at)])
                elif kind=="write_start":
                    w.start(path,at,starts.get(rid,{}).get(at))
                    if w.pending:
                        p,t,i,j,old,new=w.pending;payload=escrow(p,t,(i,j),old,new)
                        binary_size,refs,blobs,bsize,digest=w.w.wire(bodies);size=binary_size+len(payload)
                        assert c is None or size<=c
                        s["snapshots"]+=1;s["total_state_bytes"]+=size;s["total_escrow_bytes"]+=len(payload)
                        s["peak"]=max(s["peak"],size)
                elif kind=="edit":
                    if not ok:w.drop(path)
                    rr=receipt.get(rid,{}).get(str(at))
                    if rr is not None:w.read(path,at,rr)
                elif kind=="other":w.drop(path)
    pred=read(OUT/"forecast-seal.json")
    for name,s in counts.items():
        assert s["snapshots"]==pred["counts"][name]["pending"] and s["total_escrow_bytes"]==pred["counts"][name]["escrow_bytes_sum"]
        assert s["peak"]<=pred["writer_peak"][name]
    wr("capacity-audit.json",dict(program=sha(OUT/"audit_capacity.py"),counts=counts,forecasts=sha(OUT/"forecast-seal.json")))
    print("Measured",sum(s["snapshots"] for s in counts.values()),"whole live transaction state sizes.")
if __name__=="__main__":main()
