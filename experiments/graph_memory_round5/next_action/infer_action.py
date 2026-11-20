from pathlib import Path
import gzip,hashlib,json,os,sys,time,urllib.request
D=Path(__file__).resolve().parent
from_str=lambda x:json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=True)
def sha(x):return hashlib.sha256(x if isinstance(x,bytes) else x.encode()).hexdigest()
def save(p,obj):
    p=D/p;p.parent.mkdir(exist_ok=True,parents=True);tmp=p.with_suffix(".tmp");raw=from_str(obj).encode()
    tmp.write_bytes(gzip.compress(raw,mtime=0) if p.suffix==".gz" else raw);os.replace(tmp,p)
def read(p):
    p=D/p;raw=p.read_bytes();return json.loads(gzip.decompress(raw) if p.suffix==".gz" else raw)
def main(key):
    rows=read(key+"_packets.json.gz");index={};jobs={}
    for row in rows:
        i=row["id"];index[i]={}
        for a,(s,n) in row["snippets"].items():
            content="Earlier observations:\n"+s+"\n\nCurrent task and history:\n"+row["ctx"]+"\n\nPredict the next edit location."
            req=dict(model="qwen38-27b-ud-q4km",messages=[dict(role="system",content="Predict which existing code location the developer will edit next, using only the issue and observations provided. Return exactly one JSON object with keys path (repository-relative file path) and line (one-based first line of the edit). Do not output code or explanation."),dict(role="user",content=content)],temperature=0,seed=int(sha("r4java|"+i)[:7],16),max_tokens=90,repeat_penalty=1,cache_prompt=False,stream=False,chat_template_kwargs={"enable_thinking":False})
            k=sha(from_str(req));index[i][a]=k;jobs[k]=req
    save(key+"_assignment.json",index);folder=D/(key+"_calls")
    save(key+"_input_lock.json",{n:sha((D/n).read_bytes()) for n in ["PROTOCOL_RU.md","infer_action.py",key+"_data_lock.json",key+"_assignment.json",key+"_packets.json.gz"]})
    for j,k in enumerate(sorted(jobs,key=lambda k:sha("r4java-order|"+k)),1):
        path=folder/(k+".json.gz")
        if path.is_file():assert read(path)["request"]==jobs[k];continue
        for trial in range(3):
            try:
                start=time.monotonic()
                q=urllib.request.Request("http://127.0.0.1:18905/v1/chat/completions",data=from_str(jobs[k]).encode(),headers={"Content-Type":"application/json"})
                with urllib.request.urlopen(q,timeout=120) as f:o=json.load(f)
                break
            except OSError:
                if trial==2:raise
                time.sleep(2)
        save(path,{"request":jobs[k],"reply":o,"elapsed":time.monotonic()-start})
        if j==1 or j%60==0:print(key,j,len(jobs),flush=True)
    save(key+"_decisions.json",{p.name:sha(p.read_bytes()) for p in sorted(folder.glob("*.gz"))})
if __name__=="__main__":main(sys.argv[1])


