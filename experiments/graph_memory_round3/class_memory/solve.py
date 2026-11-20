"""One fresh native Qwen request for each distinct stimulus. Arm ordering has no access to test results."""
import gzip,json,sys,time,urllib.error,urllib.request
from common import D,read,save,sha
from policy import prompt
BASE="http://127.0.0.1:18891"
SYSTEM="Implement exactly the requested Python class method, using the provided interface, examples and class state. Output one complete method definition with the original name and signature. Return only Python code, without markdown or a class wrapper."
def main():
    files=["PROTOCOL.md","worker.py","prepare.py","policy.py","solve.py","common.py","visible.json","roster.json","packets.json","ClassEval_data.json"]
    lock={n:sha((D/n).read_bytes()) for n in files}
    lockpath=D/"method_lock.json"
    if lockpath.exists():assert read(lockpath)==lock
    else:save(lockpath,lock)
    items={x["id"]:x for x in read(D/"visible.json")};jobs={};index=[]
    for row in read(D/"packets.json"):
        i=row["id"];arms={}
        for a,s in row["mem"].items():
            inp=prompt(items[i],s)
            req=dict(model="qwen38-27b-ud-q4km",messages=[dict(role="system",content=SYSTEM),dict(role="user",content=inp)],
               max_tokens=384,seed=int(sha("decode|"+i)[:7],16),temperature=0,repeat_penalty=1,stream=False,
               chat_template_kwargs={"enable_thinking":False},cache_prompt=False)
            key=sha(json.dumps(req,sort_keys=True,ensure_ascii=True));jobs[key]=req;arms[a]=key
        index.append({"id":i,"arms":arms})
    save(D/"assignment.json",index)
    order=sorted(jobs,key=lambda key:sha("r3order|"+key));start=time.monotonic()
    for j,key in enumerate(order,1):
        dest=D/"calls"/(key+".json.gz")
        if dest.exists():
            assert read(dest)["key"]==key;continue
        req=jobs[key];t=time.monotonic()
        for a in range(3):
            try:
                q=urllib.request.Request(BASE+"/v1/chat/completions",data=json.dumps(req).encode(),headers={"Content-Type":"application/json"})
                with urllib.request.urlopen(q,timeout=105) as result:r=json.load(result)
                break
            except (urllib.error.URLError,TimeoutError) as exc:
                if a==2:raise
                time.sleep(2)
        save(dest,dict(key=key,request=req,reply=r,elapsed=time.monotonic()-t))
        if j==1 or not j%25:print(f"{j}/{len(order)} {time.monotonic()-start:.1f}s",flush=True)
    save(D/"decision_lock.json",{p.name:sha(p.read_bytes()) for p in sorted((D/"calls").glob("*.gz"))})
if __name__=="__main__":main()
