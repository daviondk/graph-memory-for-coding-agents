"""Build panels using visible evidence and project identity only; keep the reference next line outside the writer."""
from collections import defaultdict, Counter
from datetime import datetime,timezone
import re, gzip, hashlib, json
import pyarrow.parquet as pq
from evidence import D,R4,make,trim,TOKENFILE
from infer import save,sha
from data_io import rows, panel_name
P=R4/"repo"; BAD=re.compile(r"\b(?:shellcode|metasploit|weaponized|ammunition|malware|bioweapon|exploit(?:s|ation)?|privilege escalation|command injection|remote code execution|bypass authentication|deserialization attack|ransomware)\b",re.I)
def main():
    paths=sorted((P/"archive_inputs").glob("*.parquet"))
    clocks={p.name:hashlib.file_digest(p.open("rb"),"sha256").hexdigest() for p in paths}
    pred=P/"archive.pred.jsonl.gz"; ranks={(k,i):(repo,h,order["graph"]) for k,i,repo,h,order in map(json.loads,gzip.open(pred,"rt",encoding="utf8"))}
    raw={};queues={};excluded=[]
    for path in paths:
        panel=panel_name(path.stem)
        names=pq.read_table(path,columns=["repo_name"]).column(0).to_pylist(); buckets=defaultdict(list)
        for i,name in enumerate(names):buckets[name].append(i)
        key=lambda i:sha("r5-reader-fixed|"+panel+"|"+str(i))
        ids={i for applies in buckets.values() for i in sorted(applies,key=key)[:3]}
        queues[panel]=sorted(ids,key=key)
        for j,r in enumerate(rows(path,["code","context","repo_name","file_path"])):
            if j not in ids:continue
            code=r["code"];texts=r["context"];project=r["repo_name"]
            ctx,ct=trim("\n".join(code.splitlines()[-30:]),1024,True)
            if BAD.search("\n".join([project,r["file_path"],ctx,*texts])):excluded.append([panel,j]);continue
            rp,h,rank=ranks[panel,j];assert rp==project and sorted(rank)==list(range(len(texts)))
            raw[panel,j]=(ctx,ct,texts,project,rank,path.name)
    chosen=set(); counts={}; eligible=0
    for panelkey,quota in [("A",32),("B",16)]:
        out=[];cursor=Counter();counts=Counter()
        while True:
            n_before=len(out)
            for p,queue in queues.items():
                if counts[p]>=quota:continue
                while cursor[p]<len(queue):
                    i=queue[cursor[p]];cursor[p]+=1
                    if (p,i) not in raw:continue
                    ctx,ct,texts,project,rank,file=raw[p,i]
                    if project in chosen:continue
                    snippets,edge=make(ctx,texts,rank)
                    if panelkey=="B" and (edge is None or snippets["edge"]==snippets["local"]):continue
                    if panelkey=="B":snippets={k:snippets[k] for k in ("head","local","edge")}
                    out.append(dict(id=p+"|"+str(i),repo=project,panel=p,file=file,local_index=i,ctx=ctx,ctx_tokens=ct,rank=rank,snippets=snippets,edge_event=edge))
                    chosen.add(project);counts[p]+=1;break
            if len(out)==n_before:break
        save(panelkey+"_packets.json.gz",out);print(panelkey,len(out),dict(counts),"edge",sum(x["edge_event"] is not None for x in out),flush=True)
        save(panelkey+"_data_lock.json",{"utc":datetime.now(timezone.utc).isoformat(),"n":len(out),"strata":counts,"sha":{n:sha((D/n).read_bytes()) for n in [panelkey+"_packets.json.gz","prepare5.py","evidence.py","PROTOCOL_RU.md","infer.py"]},"source":clocks,"ranks":hashlib.file_digest(pred.open("rb"),"sha256").hexdigest(),"tokenizer":hashlib.file_digest(TOKENFILE.open("rb"),"sha256").hexdigest(),"excluded_input_rows":excluded,"used_repo_count_all_panels_so_far":len(chosen)})
if __name__=="__main__":main()

