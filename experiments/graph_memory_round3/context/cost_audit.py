"""Single-process warm-cache marginal CPU cost after old packet is available (not end-to-end latency)."""
import time,platform,statistics
from context import D,F,e,rows,stream,np,save
from expansion import select
def main():
    samples=[]
    for k in range(8):
        rr={ (r[0],r[1]):r[2]["512"]["r2f"] for r in rows(D/f"pred_{k}.jsonl.gz")}
        for o in rows(D/f"source_{k}.jsonl.gz"):
            for t,pages,idx,*_ in stream(o):
                if int(e.sha("timing|"+o["instance"]+"|"+str(t))[:8],16)%20:continue
                m={(pages[j][0],pages[j][1]+z):s for j in idx for z,s in enumerate(pages[j][4].split("\n"))}
                seed=(pages[idx[0]][0],pages[idx[0]][1],pages[idx[0]][1]) if idx else ()
                samples.append((rr[o["instance"],t],m,seed))
    timings={}
    for mode in ("iso","cap"):
        for a,m,seed in samples[:8]:select(a[0],m,seed,"balanced",a[1] if mode=="iso" else 512,a[2] if mode=="iso" else 512)
    for ix,(a,m,seed) in enumerate(samples):
        for mode in (("iso","cap") if ix%2 else ("cap","iso")):
            start=time.process_time_ns();select(a[0],m,seed,"balanced",a[1] if mode=="iso" else 512,a[2] if mode=="iso" else 512)
            timings.setdefault(mode,[]).append((time.process_time_ns()-start)/1e6)
    save("marginal_cpu.json",dict(n=len(samples),platform=platform.platform(),python=platform.python_version(),excludes="generation of original packet, network, solver, trajectory parsing",milliseconds={a:{"median":float(np.median(v)),"p90":float(np.percentile(v,90)),"mean":float(np.mean(v))} for a,v in timings.items()}))
if __name__=="__main__":main()
