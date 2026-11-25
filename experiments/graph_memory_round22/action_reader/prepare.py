"""Construct fixed-width anonymous action choices without the observed used/generation join."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path

D=Path(__file__).resolve().parent
OBS=D.parent/"observed_flow"
C=Path("D:/CodexResearch/x20-observed-r-flow")
LETTERS="ABCD"
SYS=("You inspect an execution log. Choose one recorded earlier operation to open in order to inspect a scalar input to the current operation. "
     "Later operations may re-use names or values. Each card shows age in operations, number of matching variable names, "
     "number of matching literal values, and whether it is the latest writer of a matching name. Return only its letter.")
def h(x):return hashlib.sha256(x).hexdigest()
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def write(p,obj):
    b=(json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def key(event):return (event["last"],event["names"],event["values"],-event["age"])
def main():
    source=C/"flow-packets.json"
    audit={r["trace"]:r["family"] for r in read(OBS/"corpus-audit.json")}
    grouped=defaultdict(list);alln=0
    for record in read(source):
        t=record["trace"];family=audit[t];saved=[];last={}
        for e in record["events"]:
            step=e["id"];names=set(e["symbols"]);values=set(e["literals"])
            if (names or values) and len(saved)>=4:
                cards=[{"producer":k,"age":step-k,"last":int(any(last.get(n)==k for n in names & wn)),
                       "names":len(names & wn),"values":len(values & wv)} for k,wn,wv in saved]
                if any(x["names"]+x["values"] for x in cards):
                    case=t+"/"+str(step);alln+=1
                    chosen={"fifo":cards[-4:],"name_index":sorted(cards,key=key,reverse=True)[:4]}
                    row={"case":case,"t":t,"family":family,"step":step,"arms":{}}
                    for arm,sub in chosen.items():
                        xs=sorted(sub,key=lambda x:h(("card-22|"+case+"|"+str(x["producer"])).encode()))
                        assert max(v["age"] for v in xs)<1000000 and max(max(v["names"],v["values"]) for v in xs)<1000
                        row["arms"][arm]={"cards":xs,"rule":max(xs,key=key)["producer"]}
                    grouped[family].append(row)
            if e["write"]:
                wnames={w[1] for w in e["write"] if w[1]};wvals={w[0] for w in e["write"]}
                saved.append((step,wnames,wvals))
                for n in wnames:last[n]=step
    rows=[r for fam,parts in sorted(grouped.items()) for r in sorted(parts,key=lambda r:h(("action-v1|"+r["case"]).encode()))[:4]]
    tasks={}
    for row in rows:
        for arm in row["arms"].values():
            arm["prompts"]={}
            for order,sub in [("normal",arm["cards"]),("reverse",arm["cards"][::-1])]:
                msg="Read one source. The four candidates are:\n"+"\n".join(f"{c}: age={v['age']:06d} names={v['names']:03d} values={v['values']:03d} last={v['last']}" for c,v in zip(LETTERS,sub,strict=True))
                digest=h(msg.encode());tasks[digest]=msg;arm["prompts"][order]=digest
    assert len(set(len(v.encode()) for v in tasks.values()))==1
    write(D/"cards.json.gz",rows);write(D/"requests.json.gz",tasks)
    write(D/"selection-lock.json",{"families":len(grouped),"eligible_before_family_cap":alln,"cases":len(rows),"unique_prompts":len(tasks),
          "prompt_bytes":len(next(iter(tasks.values())).encode()),"cards":h((D/"cards.json.gz").read_bytes()),"requests":h((D/"requests.json.gz").read_bytes()),
          "input":h(source.read_bytes()),"code":h(Path(__file__).read_bytes()),"protocol":h((D/"PROTOCOL_RU.md").read_bytes())})
    print("cases",len(rows),"prompts",len(tasks),"families",len(grouped),flush=True)
if __name__=="__main__":main()
