"""Read all measurements and independently reconcile each native syscall trace with its request."""
from collections import Counter,defaultdict
from decimal import Decimal
import gzip,hashlib,json,re,statistics
from pathlib import Path
D=Path(__file__).resolve().parent
def load(p):
    data=p.read_bytes();return json.loads(gzip.decompress(data) if p.suffix==".gz" else data)
def summary(rs):
    return dict(n=len(rs),ok=sum(v["actual"]==v["truth"] for v in rs),hit=sum(r["hit"] for r in rs),payload=sum(v["cost"] for v in rs),text=sum(v["view"] for v in rs),median_us=statistics.median(v["elapsed_ns"]/1e3 for v in rs),mean_us=statistics.mean(v["elapsed_ns"]/1e3 for v in rs))
def reconcile(panel):
    bills=load(panel/"trace_receipts.json.gz");bymap=defaultdict(list)
    for r in bills:bymap[r["arm"],r["filename"]].append(r)
    hits=load(panel/"trace_scores.json.gz")
    sums=defaultdict(Counter);native_logs=[]
    for arm in ("native","ctime_id"):
        for line in load(panel/(arm+"_file_syscalls.json.gz")):
            m=re.match(r"^\d+ ([\d.]+) (\w+)\((.*)$",line)
            if not m:continue
            t=int(Decimal(m[1])*1000000000);op=m[2];args=m[3]
            # Limit to syscalls on the target fd or the path argument itself.
            # IPC carrying the target file name in its payload is excluded.
            direct=re.match(r'(?:\d+<|\x22|AT_FDCWD[^,]*,\s*\x22)(/[^<\x22>]+/case_\d{3}\.py)(?:>|\x22)',args)
            if not direct:continue
            name=Path(direct[1]).name
            associated=[r for r in bymap[arm,name] if r["clock_open_ns"]-1000<=t<=r["clock_close_ns"]+1000]
            assert len(associated)==1,(line,arm,name)
            r=associated[0];panelname,case=r["case"].split("|",1)
            key=(r["stage"],panelname,case,arm)
            sums[key][op]+=1
            if op in ("read","pread64","readv"):
                result=re.search(r"\) = (\d+)$",args);assert result,line
                sums[key]["bytes"]+=int(result[1])
    for item in hits:
        key=("repeat",item["panel"],item["case"],item["arm"])
        actual=sums[key]
        assert actual["bytes"]==item["cost"],(key,actual,item)
        if item["hit"]:assert not actual
        else:assert actual["open"]+actual["openat"]>=1 and actual["read"]>=1
    for (stage,panelname,case,arm),counts in sums.items():
        native_logs.append({"stage":stage,"panel":panelname,"case":case,"arm":arm,"syscounts":counts})
    (panel/"syscall_counts.json.gz").write_bytes(gzip.compress(json.dumps(native_logs).encode(),mtime=0))
    result={}
    for pp in ("controlled","released"):
        result[pp]={}
        for arm in ("native","ctime_id"):
            total=Counter()
            for (stage,panelname,case,what),ct in sums.items():
                if (stage,panelname,what)==("repeat",pp,arm):total.update(ct)
            total["wrapper_stat"]=sum(r["panel"]==pp and r["arm"]==arm for r in hits) if arm=="ctime_id" else 0
            result[pp][arm]=dict(total)
    return result
def main():
    stats={}
    for fs in ("ext4","tmpfs"):
        panel=D/fs;rs=load(panel/"metrics.json.gz");ss=load(panel/"stress.json.gz");out={}
        for g in ("controlled","released"):
            out[g]={m:summary([r for r in rs if r["panel"]==g and r["arm"]==m]) for m in ("native","full","mtime_size","mtime_id","ctime_id")}
        out["bursts"]={}
        for mode in ("replace_restore","atomic_restore"):
            out["bursts"][mode]={}
            for a in ("native","ctime_id"):
                rows=[s for s in ss if s["arm"]==a and s["mode"]==mode]
                out["bursts"][mode][a]={"n":len(rows),"distinct_content_events":sum(r["source_change"] for r in rows),"correct":sum(v["visible_sha"]==v["truth_sha"] for v in rows),"matching_stamp":sum(r["ctime_collision"] for r in rows),"cached":sum(r["hit"] for r in rows)}
        out["native_syscalls"]=reconcile(panel);stats[fs]=out;print(fs,json.dumps(out))
    (D/"results.json").write_text(json.dumps(stats,indent=1))
if __name__=="__main__":main()
