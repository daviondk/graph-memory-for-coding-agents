import gzip,hashlib,json,time,urllib.request
from pathlib import Path
D=Path(__file__).resolve().parent
def serial(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
def sha(x):return hashlib.sha256(x).hexdigest()
def main():
    ids=json.loads((D/"cohort.json").read_text())["ids"][:12];jobs={};assignment={}
    for i in ids:
        d=json.loads(gzip.decompress((D/"tasks"/i/"packets.json.gz").read_bytes()))
        assignment[i]={}
        for arm in ("flat","evidence"):
            packet=d["packets"][arm]
            sysmsg="Repair a mathematics library using code fragments observed by a previous developer. Output only JSON with an edits array. Each item has path (as shown), old (one exact, unique contiguous substring in the unmodified file) and new (replacement). Preserve literal spaces and indentation. Use minimal edits. Give your best fix."
            user="Issue:\n"+d["issue"]+"\n\nObserved Python code:\n"+packet
            req=dict(model="qwen38-27b-ud-q4km",messages=[dict(role="system",content=sysmsg),dict(role="user",content=user)],temperature=0,seed=int(sha(i.encode())[:7],16),max_tokens=850,repeat_penalty=1,cache_prompt=False,stream=False,chat_template_kwargs={"enable_thinking":False})
            key=sha(serial(req));jobs[key]=req;assignment[i][arm]=key
    (D/"assign.json").write_bytes(serial(assignment))
    names=["build_memory.py","infer.py","PROTOCOL_RU.md","collect_tasks.py","cohort.json","assign.json"]
    lock={k:sha((D/k).read_bytes()) for k in names}
    lock["packets"]={i:sha((D/"tasks"/i/"packets.json.gz").read_bytes()) for i in ids}
    (D/"input_lock.json").write_bytes(serial(lock));folder=D/"calls";folder.mkdir(exist_ok=True)
    for j,k in enumerate(sorted(jobs,key=lambda s:sha(("r6|"+s).encode())),1):
        path=folder/(k+".json.gz")
        if path.exists():assert json.loads(gzip.decompress(path.read_bytes()))["request"]==jobs[k];continue
        for trial in range(3):
            try:
                start=time.monotonic();r=urllib.request.Request("http://127.0.0.1:18907/v1/chat/completions",data=serial(jobs[k]),headers={"Content-Type":"application/json"})
                with urllib.request.urlopen(r,timeout=240) as f:data=json.load(f)
                break
            except OSError:
                if trial==2:raise
                time.sleep(2)
        path.write_bytes(gzip.compress(serial({"request":jobs[k],"response":data,"elapsed":time.monotonic()-start}),mtime=0))
        print(j,len(jobs),round(time.monotonic()-start,2),flush=True)
if __name__=="__main__":main()

