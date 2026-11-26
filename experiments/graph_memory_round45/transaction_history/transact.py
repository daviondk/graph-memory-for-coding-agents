"""One global writer. Charged action escrow makes stale rows unavailable while preserving their bytes."""
from inputs import *
def escrow(path,at,ids,old,new):
    out=bytearray(b"P"+bytes.fromhex(path)+struct.pack(">I",at))
    for s in (*ids,old,new):
        b=s.encode();out.extend(struct.pack(">I",len(b)));out.extend(b)
    return bytes(out)
class Transaction:
    def __init__(self,mode,cap):
        self.mode=mode;self.cap=cap;self.w=Writer("lru",cap);self.pending=None;self.depth={};self.stats=Counter();self.peak=8
    def trim_depth(self):self.depth={k:d for k,d in self.depth.items() if k in self.w.rows and d}
    def drop(self,path):
        self.w.remove_path(path);self.trim_depth()
    def clear_pending(self):
        if self.pending:
            self.w.cap=self.cap;self.pending=None
    def cancel(self):
        if self.pending:
            self.drop(self.pending[0]);self.clear_pending();self.stats["nonadjacent_or_unmatched"]+=1
    def clear(self):self.clear_pending();self.w.clear();self.depth.clear()
    def read(self,path,at,values):
        self.w.read(path,at,values)
        for n,d,sz,ok in values:
            if ok:self.depth.pop((path,n),None)
        self.trim_depth()
    def start(self,path,at,act):
        assert self.pending is None
        if self.mode=="reset" or act is None:
            self.drop(path);return
        _,i,j,old,new=act;e=escrow(path,at,(i,j),old,new);sz=len(e)
        if self.cap is not None and sz+8>self.cap:
            self.stats["escrow_exceeds_capacity"]+=1;self.drop(path);return
        if self.cap is not None:self.w.cap=self.cap-sz
        old_evictions=self.w.evicted;self.w.read(path,at,[]);self.trim_depth()
        self.stats["escrow_evictions"]+=self.w.evicted-old_evictions
        amounts={v[0]:v[1] for v in self.w.rows.values()}
        physical=8+50*len(self.w.rows)+sum(2+n for n in amounts.values())+sz
        assert self.cap is None or physical<=self.cap
        self.pending=(path,at,i,j,old,new);self.peak=max(self.peak,physical);self.stats["pending"]+=1;self.stats["escrow_bytes_sum"]+=sz
    def before(self,at,kind,path,end):
        if not self.pending:return
        p,prior,i,j,old,new=self.pending
        if kind!="edit" or at!=prior+1 or p!=path or end is None or (end[1],end[2])!=(i,j):
            self.cancel();return
        self.clear_pending();k=locate(end[3],new);self.stats["matched_adjacent"]+=1
        if k is None or self.mode=="charged":
            self.stats["unanchored" if k is None else "charged_reset"]+=1;self.drop(p);return
        end_old=k+old.count("\n");delta=new.count("\n")-old.count("\n");inside={}
        if self.mode=="local":_,inside,_=match(equality_tokens(old),equality_tokens(new))
        kept={};depth={}
        for key,value in self.w.rows.items():
            if key[0]!=p:continue
            pos=project(key[1],key[1],k,end_old,delta,inside)
            if pos:
                dest=(p,pos[0]);assert dest not in kept
                kept[dest]=value;depth[dest]=self.depth.get(key,0)+1;self.stats["rebased_rows"]+=1
        self.drop(p);self.w.rows.update(kept);self.depth.update(depth);self.stats["anchored"]+=1
        return True

def main():
    assert sha(OUT/"PROTOCOL_RU.md")=="011f88e8bb79b7c135f04e906d6999d90b46e7e07e69a6d76a3c9f67ee5b35f5"
    st=time.perf_counter();frames,views,receipt,starts,ends,bodies=collect();src_t=time.perf_counter()-st;st=time.perf_counter()
    targets=defaultdict(dict)
    for row in signed(G,"selections.json.gz"):targets[row["run"]][row["at"]]=row
    packets=signed(F,"packets.json.gz");old=signed(R,"forecasts.json.gz");actions=signed(C,"action-lines.json.gz")
    pred={};stat=defaultdict(Counter);peaks=Counter()
    for rid,seq in frames.items():
        methods={(m,cap):Transaction(m,cap) for m in ("reset","charged","range","local") for cap in (*CAPS,None)}
        for at,kind,path in seq:
            end=ends.get(rid,{}).get(at);active={}
            for key,w in methods.items():active[key]=w.before(at,kind,path,end)
            if kind in ("gap","barrier","finish"):
                for w in methods.values():w.clear()
                continue
            if at in targets[rid]:
                row=targets[rid][at];k=h(rid+"/"+str(row["receipt"]));p=packets[k];action=actions[k];_,mapping,_=match(action["old"],action["new"])
                assert kind=="write_start";catalog={};arms={}
                for (m,cap),w in methods.items():
                    assert w.pending is None
                    ar=readback(w.w,bodies,path,row,dict(p["receipt"]),mapping,catalog)
                    li=list(catalog);ar["depth"]=[w.depth.get((path,li[j][0]),0) for j in ar["all"]]
                    if m=="reset":
                        expected=old[k]["arms"][label("joint",cap)]
                        assert ar["wire"]==expected["wire"] and ar["emitted_bytes"]==expected["emitted_bytes"]
                        for t in ("all","read"):assert [list(li[i]) for i in ar[t]]==[old[k]["candidates"][j] for j in expected[t]]
                    arms[label(m,cap)]=ar
                pred[k]=dict(repo=p["repo"],issue=p["issue"],group=p["group"],held=p["held"],run=rid,at=at,candidates=list(catalog),arms=arms)
            if kind=="read":
                for w in methods.values():w.read(path,at,views[rid][str(at)])
            elif kind=="write_start":
                for w in methods.values():w.start(path,at,starts.get(rid,{}).get(at))
            elif kind=="edit":
                for key,w in methods.items():
                    if not active[key]:w.drop(path)
                    rows=receipt.get(rid,{}).get(str(at))
                    if rows is not None:w.read(path,at,rows)
            elif kind=="other":
                for w in methods.values():w.drop(path)
        for (m,cap),w in methods.items():
            name=label(m,cap);stat[name].update(w.stats);peaks[name]=max(peaks[name],w.peak,w.w.max_size)
    assert set(pred)==set(old)
    wr("forecasts.json.gz",pred);wr("forecast-seal.json",dict(forecasts=sha(OUT/"forecasts.json.gz"),input=sha(OUT/"input-seal.json"),program=sha(OUT/"transact.py"),
       protocol=sha(OUT/"PROTOCOL_RU.md"),counts=stat,writer_peak=peaks,acquire_seconds=src_t,simulation_seconds=time.perf_counter()-st))
    print("Verified reset control and sealed",len(pred),"x 16 predictions.")
if __name__=="__main__":main()
