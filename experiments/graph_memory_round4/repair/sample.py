import json,time,urllib.request
from base import D,read,save,sha,stable
from solve import request
def main():
    jobs={};assign={}
    for task in read("packets.json.gz"):
        i=task["id"];assign[i]=[]
        for sample in range(2):
            req=request(task,"empty")
            req.update(temperature=.7,top_p=.95,seed=int(sha("r4-blind|"+str(sample)+"|"+i)[:7],16))
            k=sha(stable(req));jobs[k]=req;assign[i].append(k)
    save("sample_assignment.json",assign)
    files=["RERANK_PROTOCOL_RU.md","sample.py","solve.py","sample_assignment.json","inference_lock.json"]
    lock={n:sha((D/n).read_bytes()) for n in files}
    if (D/"sample_lock.json").exists():assert read("sample_lock.json")==lock
    else:save("sample_lock.json",lock)
    for j,key in enumerate(sorted(jobs,key=lambda k:sha("r4-blind-order|"+k)),1):
        dst="sample_calls/"+key+".json.gz"
        if (D/dst).exists():assert read(dst)["request"]==jobs[key];continue
        for trial in range(3):
            try:
                started=time.monotonic();q=urllib.request.Request("http://127.0.0.1:18904/v1/chat/completions",data=stable(jobs[key]).encode(),headers={"Content-Type":"application/json"})
                with urllib.request.urlopen(q,timeout=120) as f:reply=json.load(f)
                break
            except OSError:
                if trial==2:raise
                time.sleep(2)
        save(dst,{"request":jobs[key],"reply":reply,"elapsed":time.monotonic()-started})
        if j==1 or j%25==0:print(j,len(jobs),flush=True)
    save("sample_decisions.json",{str(p.relative_to(D)):sha(p.read_bytes()) for p in sorted((D/"sample_calls").glob("*.json.gz"))})
if __name__=="__main__":main()

