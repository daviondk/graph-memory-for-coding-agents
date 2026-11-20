"""Post-result CPU cost measurement on prefix-selected windows. Quantiles, same version and process."""
import collections,hashlib,json,os,platform,statistics,time
from common import *
from policy import *
from pipeline import data,snapshots

def main():
    model=json.loads((ROOT/'model.json').read_bytes());target=[]
    for k in range(8):
        for r in data('test',k):
            for t in range(4,len(r['events']),4):
                h=hashlib.sha256((r['instance']+'|'+str(t)+'|s5cost').encode()).hexdigest();target.append((h,r['instance'],t))
    wanted={(i,t) for h,i,t in sorted(target)[:384]};times=collections.defaultdict(list);extra=[]
    for k in range(8):
        for row in data('test',k):
            ts={t for i,t in wanted if i==row['instance']}
            if not ts:continue
            for t,ss,m in snapshots(row):
                if t not in ts:continue
                rs=pages(ss['rebase']);extra.append((len(rs),sum(len(v[4].encode()) for v in rs)))
                def call(name):
                    start=time.perf_counter_ns();cs=costs(rs)
                    if name=='tail':greedy_base(rs,order(rs,m,'tail'),cs,512)
                    else:
                        fs=features(rs,m,t,row['issue'],order(rs,m)[:CAP]);pr=proposals(rs,fs,model);joint_fill(rs,cs,pr,512)
                    return (time.perf_counter_ns()-start)/1e6
                # Interleaved warm-cache latency, states built outside. Both arms first warmed once.
                for name in ['joint','tail']:call(name)
                order_= ['joint','tail'] if (t//4)%2 else ['tail','joint']
                for name in order_:times[name].append(statistics.median(call(name) for _ in range(3)))
    def stats(v):
        v=sorted(v);return {'n':len(v),'median':statistics.median(v),'p95':v[int(len(v)*.95)],'mean':statistics.mean(v)}
    result={'condition':'warm tokenization caches; 3 repeats per arm, medians within window; extraction of pages outside timing; concurrent host work possible; no extra model calls. Includes all prefix-hash-selected windows incl empty.','ms':{n:stats(t) for n,t in times.items()},'pages':stats([r[0] for r in extra]),'retained_text_bytes':stats([r[1] for r in extra]),'python':platform.python_version(),'cpu':platform.processor()}
    (ROOT/'cpu_cost.json').write_text(json.dumps(result,indent=1));print(result)
if __name__=='__main__':main()
