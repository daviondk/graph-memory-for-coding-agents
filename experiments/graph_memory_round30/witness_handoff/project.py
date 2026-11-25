"""Project read addresses and split prefix from the first later read. Source code is only read as text."""
from collections import defaultdict,Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlopen
from urllib.parse import quote
from pathlib import Path
from inventory import *
from hashlib import sha256
import time,shutil
def fetch(row):
    repo,commit,path=row;key=h("\0".join(row));own=P/"base"/key;known=SWE/"files"/key
    try:
        if not own.exists():
            if known.exists():shutil.copyfile(known,own)
            else:
                for i in range(3):
                    try:
                        with urlopen(f"https://raw.githubusercontent.com/{repo}/{commit}/"+quote(path),timeout=18) as z:b=z.read(3*1024*1024+1)
                        if len(b)>3*1024*1024:raise RuntimeError("exceeds3MiB")
                        own.write_bytes(b);break
                    except OSError:
                        if i==2:raise
                        time.sleep(.3*(i+1))
        return dict(key=key,repo=repo,commit=commit,path=path,sha=sha256(own.read_bytes()).hexdigest(),bytes=own.stat().st_size)
    except (ValueError,OSError,RuntimeError) as e:return dict(key=key,repo=repo,commit=commit,path=path,error=type(e).__name__)
def collect(people,limit):
    events=[];future=[]
    for w,steps in sorted(people.items()):
        for j,(local,byfile) in enumerate(sorted(steps.items())):
            if j>limit:break
            event=dict(w=w,j=j,local=local,r=[(path,items) for path,items in sorted(byfile.items())])
            (events if j<limit else future).append(event)
    events.sort(key=lambda e:(e["j"],e["w"]))
    return events,future
def swe_project():
    meta={h(r["instance_id"]):r for r in pq.read_table(SWE/"verified.parquet",columns=["repo","instance_id","base_commit"]).to_pylist()}
    inverted={}
    for raw in (SWE/"swe-explore.jsonl").open(encoding="utf8"):
        row=json.loads(raw);inverted[h(row["instance_id"])]={h(p):p for p in row["read_step_info"] if prod(p)}
    issues=get(P/"swe-events.json.gz");refs=set();basis={}
    for it in issues:
        q=it["issue"];m=meta[q];by=defaultdict(lambda:defaultdict(lambda:defaultdict(list)))
        for path,worker,step,low,high in it["events"]:by[worker][step][path].append((low,high))
        ev,nexts=collect(by,3);basis[q]=(ev,nexts)
        for v in ev+nexts:
            for ph,_ in v["r"]:refs.add((m["repo"],m["base_commit"],inverted[q][ph]))
    (P/"base").mkdir(exist_ok=True)
    with ThreadPoolExecutor(8) as ex:filemap=list(ex.map(fetch,sorted(refs)))
    paths={r["key"]:r for r in filemap};pm=save(P/"base-source-map.json",filemap)
    eligibility=Counter();rows=[];targets=[];files={}
    for q,(ev,nexts) in basis.items():
        m=meta[q];prefix=[];future=[]
        for event,isfuture in [(e,False) for e in ev]+[(e,True) for e in nexts]:
            target=[];ranges=[]
            for ph,spans in event["r"]:
                path=inverted[q][ph];key=h("\0".join((m["repo"],m["base_commit"],path)));ref=paths[key]
                for lo,hi in spans:
                    if "sha" not in ref:eligibility["unavailable_range"]+=1;continue
                    if key not in files:
                        data=(P/"base"/key).read_bytes()
                        try: text=data.decode("utf8")
                        except UnicodeDecodeError:text=None
                        files[key]={i:(h(s),len(s.encode())) for i,s in lines(text,1)} if text is not None else {}
                    fl=files[key];items=[[i,*fl[i]] for i in range(lo,min(max(fl,default=0),hi)+1) if i in fl]
                    if not items:eligibility["no_eligible_lines_"+str(isfuture)]+=1
                    if items:ranges.append((key,items))
                    if len(items)>=2:target.append((key,items[0],items[-1]))
                    elif isfuture:eligibility["future_lt_two_lines"]+=1
            if isfuture:future.extend(target)
            else:prefix.append(dict(w=event["w"],j=event["j"],local=event["local"],r=ranges))
        rows.append(dict(id=q,events=prefix));targets.append(dict(id=q,future=future))
    return rows,targets,dict(source_map_sha=pm,base_files=len(filemap),absent=sum("sha" not in r for r in filemap),counts=eligibility)
def ise_project(panel="ise"):
    rows=[];targets=[]
    for r in get(P/(panel+"-events.json.gz")):
        if len(r["events"])<2:continue
        def convert(e,i):return dict(w="session",j=i,local=e["id"],r=[(e["path"],e["lines"])])
        prefix=[convert(e,i) for i,e in enumerate(r["events"][:2])];f=[]
        if len(r["events"])>=3:
            v=r["events"][2];ls=v["lines"]
            if len(ls)>=2:f.append((v["path"],ls[0],ls[-1]))
        rows.append(dict(id=r["id"],events=prefix));targets.append(dict(id=r["id"],future=f))
    return rows,targets,dict()
def main(p):
    obs,targets,extra=swe_project() if p=="swe" else ise_project(p)
    rec=dict(n=len(obs),prefix_sha=save(P/(p+"-prefix.json.gz"),obs),target_sha=save(P/(p+"-targets.json.gz"),targets),protocol=sha256((D/"PROTOCOL_RU.md").read_bytes()).hexdigest(),**extra)
    save(D/(p+"-projection.json"),rec);print(p,len(obs),extra)
if __name__=="__main__":main(sys.argv[1])

