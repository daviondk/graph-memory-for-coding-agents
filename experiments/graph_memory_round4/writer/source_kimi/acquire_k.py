"""Normalize repeated tool IDs strictly inside one assistant turn and reuse the original independent projection."""
import copy,gzip,hashlib,json,sys,time,urllib.request,urllib.error,concurrent.futures
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent))
from shared import A,B,D,read,save,sha,write
sys.path.insert(0,str(A));import acquire
RUN="20250804_codesweep_sweagent_kimi_k2_instruct"
ROOT="https://swe-bench-submissions.s3.amazonaws.com/verified/"+RUN+"/trajs/"
def localize(s):
    turno=-1;valid=set();tot=0;driver_count=Counter()
    for m in s.get("history",[]):
        if m.get("role")=="assistant":
            turno+=1;valid=set()
            for tool in (m.get("tool_calls") or []):
                key=tool.get("id")
                if not key:continue
                if key in valid:return False,0
                valid.add(key);driver_count[key]+=1
                tool["id"]=str(turno)+"|"+key
        elif m.get("role")=="tool":
            keys=m.get("tool_call_ids",[])
            if any(x not in valid for x in keys):return False,0
            m["tool_call_ids"]=[str(turno)+"|"+key for key in keys]
    return True,sum(v-1 for v in driver_count.values() if v>1)
def grab(meta):
    i=meta["instance_id"];url=ROOT+i+".traj";rc=dict(id=i,url=url)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"public-memory-study"}),timeout=35) as f:
                if int(f.headers.get("content-length",-1))>acquire.LIMIT:return None,{**rc,"status":"oversize"}
                raw=f.read(acquire.LIMIT+1)
                if len(raw)>acquire.LIMIT:return None,{**rc,"status":"oversize"}
            rc["sha256"]=hashlib.sha256(raw).hexdigest();rc["bytes"]=len(raw);s=json.loads(raw);del raw
            ok,n=localize(s);rc["reused_ids"]=n
            if not ok:return None,{**rc,"status":"invalid_turn_match"}
            projected,ct=acquire.project(s,meta);rc["counts"]=dict(ct)
            return projected,{**rc,"status":"ok" if projected else "filtered"}
        except urllib.error.HTTPError as err:
            if err.code in (403,404) or attempt==2:return None,{**rc,"status":str(err.code)}
        except (OSError,ValueError,KeyError) as err:
            if attempt==2:return None,{**rc,"status":type(err).__name__}
        time.sleep(.3)
def main():
    candidates={r["instance_id"]:r for p in (A,B) for r in read(p/"selection.json")}
    assert len(candidates)==294
    ns=Counter();rows=[]
    for i in sorted(candidates,key=lambda x:hashlib.sha256(("r4-kimi|"+x).encode()).hexdigest()):
        r=candidates[i]
        if ns[r["repo"]]>=10:continue
        ns[r["repo"]]+=1;rows.append(r)
    save(HERE/"selection.json",rows);save(HERE/"selection_receipt.json",dict(n=len(rows),repos=ns,protocol=sha(HERE/"PROTOCOL_RU.md"),run=RUN))
    files=[gzip.open(HERE/f"source_{k}.jsonl.gz","wt",encoding="utf8",compresslevel=3) for k in range(8)];rec=[]
    with concurrent.futures.ThreadPoolExecutor(10) as pool:
        for j,(q,s) in enumerate(pool.map(grab,rows)):
            rec.append(s)
            if q:write(files[j%8],q)
            if (j+1)%20==0:print(j+1,Counter(r["status"] for r in rec),flush=True)
    for f in files:f.close()
    save(HERE/"receipts.json",rec);save(HERE/"download_summary.json",dict(n=len(rec),statuses=Counter(r["status"] for r in rec)))
if __name__=="__main__":main()
