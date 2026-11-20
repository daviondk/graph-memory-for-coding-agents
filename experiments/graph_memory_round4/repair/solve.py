"""One local inference per distinct fully-specified request. Seal the complete output before scoring."""
from base import D,read,save,sha,stable
from policy import pretty
import json,time,urllib.request,urllib.error
SYSTEM="Fix one logical defect in the supplied ordinary Python function. The only surviving CI notes are old assertions with trusted expected values. PASS and FAIL report the old implementation. Preserve the API. Return complete executable Python source including required imports. No explanation or test code."
def request(row,arm):
    content="Current implementation:\n"+row["source"]+"\n\nRetained observations:\n"+pretty(row["memory"][arm])
    return {"model":"qwen38-27b-ud-q4km","messages":[{"role":"system","content":SYSTEM},{"role":"user","content":content}],
        "temperature":0,"max_tokens":640,"repeat_penalty":1,"seed":int(sha("q4s|"+row["id"])[:7],16),"cache_prompt":False,"stream":False,"chat_template_kwargs":{"enable_thinking":False}}
def main():
    packets=read("packets.json.gz");jobs={};index={}
    for p in packets:
        index[p["id"]]={}
        for a in ["empty","failed","union"]:
            req=request(p,a);key=sha(stable(req));jobs[key]=req;index[p["id"]][a]=key
    save("assign.json",index)
    names=["writer_lock.json","write_receipt.json","packets.json.gz","solve.py","assign.json","PROTOCOL_RU.md"]
    lock={n:sha((D/n).read_bytes()) for n in names}
    if (D/"inference_lock.json").exists():assert read("inference_lock.json")==lock
    else:save("inference_lock.json",lock)
    base="http://127.0.0.1:18904"
    for tick in range(120):
        try:
            with urllib.request.urlopen(base+"/health",timeout=2) as f:
                if f.status==200:break
        except OSError:time.sleep(1)
    started=time.monotonic()
    for j,key in enumerate(sorted(jobs,key=lambda k:sha("r4-order|"+k)),1):
        name="calls/"+key+".json.gz"
        if (D/name).is_file():
            assert read(name)["request"]==jobs[key];continue
        for trial in range(3):
            try:
                t=time.monotonic()
                q=urllib.request.Request(base+"/v1/chat/completions",data=stable(jobs[key]).encode(),headers={"Content-Type":"application/json"})
                with urllib.request.urlopen(q,timeout=115) as f:reply=json.load(f)
                break
            except OSError as e:
                if trial==2:raise
                time.sleep(2)
        save(name,{"request":jobs[key],"reply":reply,"elapsed":time.monotonic()-t})
        if j==1 or j%20==0:print(j,len(jobs),round(time.monotonic()-started,1),flush=True)
    save("predictions_lock.json",{str(f.relative_to(D)):sha(f.read_bytes()) for f in sorted((D/"calls").glob("*.json.gz"))})
    print("sealed",len(jobs),flush=True)
if __name__=="__main__":main()

