"""Separate the observed predecessor timeline from real delivered prompts and successor read outcomes."""
from source import *
import re
from collections import defaultdict
HEADER=re.compile(r"cat -n`? on\s+(/(?:testbed|workspace)/[^:\s]+\.py):\s*$")
NUMBER=re.compile(r"^ *([0-9]+)\t(.*)$")
def norm(p):
    if not p or not isinstance(p,str):return None
    for prefix in ("/testbed/","/workspace/"):
        if p.startswith(prefix):
            rel=p[len(prefix):]
            return rel if prod(rel) else None
    return None
def informative(s):return 24<=len(s.encode())<=320 and len(set(re.findall(r"[A-Za-z_]{2,}",s.lower())))>=3 and not re.search(r"licensed under|copyright|all rights reserved|SPDX-license|clipped|truncated",s,re.I) and not RISK.search(s)
def extract_lines(text):
    output=[]
    for line in text.splitlines():
        m=NUMBER.fullmatch(line)
        if m is not None and informative(m[2]):output.append([int(m[1]),m[2]])
    return output
def section(text):
    m=re.search(r"=== (PREVIOUS AGENT [^\n=]+?) BEGINS ===\n(.*?)\n=== \1 ENDS ===",text.replace("\r\n","\n"),re.S)
    return m[2] if m else ""
def strict(text):
    active=None;out=set()
    for line in text.splitlines():
        head=HEADER.search(line)
        if head:
            active=norm(head[1]);continue
        row=NUMBER.fullmatch(line)
        if row and active:
            if informative(row[2]):out.add((active,int(row[1]),h(row[2])))
        else:active=None
    return out
def main():
    runs,meta=cohort();ck={};steps=defaultdict(list);futu={};prompts={};native={};seen=Counter();qdom={};typ=Counter()
    for x in pq.read_table(P/"data/checkpoints/data-00000.parquet",columns=["initial_run_id","checkpoint_id","step"]).to_pylist():
        if x["initial_run_id"] in runs:ck[(x["initial_run_id"],x["checkpoint_id"])]=x["step"]
    cap={p:max(s for (a,k),s in ck.items() if a==p) for p,_ in ck}
    for f in sorted((P/"data/handoffs").glob("*.parquet")):
        for x in pq.read_table(f,columns=["run_id","rendered_prompt","handoff_json"]).to_pylist():
            rid=x["run_id"]
            if rid not in runs or runs[rid]["role"]!="takeover":continue
            text=x["rendered_prompt"];j=json.loads(x["handoff_json"]);assert j["prompt"]==text and j["view"]==runs[rid]["handoff_view"]
            native[rid]=dict(sha=h(text),section=section(text),prompt_chars=len(text),prompt=text)
    files=get(P/"files.json")["events"]
    for i,ref in enumerate(files):
        path=P/ref["file"];assert sha(path)==ref["sha"];pf=pq.ParquetFile(path)
        cols=["run_id","event_index","step","event_type","source","source_json_valid","event_json"]
        for bat in pf.iter_batches(batch_size=96,columns=cols):
            ids=bat.column("run_id").to_pylist();inds=bat.column("event_index").to_pylist();times=bat.column("step").to_pylist();types=bat.column("event_type").to_pylist();who=bat.column("source").to_pylist();valid=bat.column("source_json_valid").to_pylist()
            for j,rid in enumerate(ids):
                if rid not in runs or not valid[j]:continue
                run=runs[rid];pred=(run["role"]=="predecessor");idx=inds[j];step=times[j]
                if not pred and types[j]=="MessageEvent" and str(who[j]).lower()=="user" and (rid not in prompts or idx<prompts[rid][0]):
                    e=json.loads(bat.column("event_json")[j].as_py());llm=e.get("raw",{}).get("llm_message",{})
                    if llm.get("role")!="user":continue
                    texts=[t["text"] for t in llm.get("content",[]) if isinstance(t,dict) and t.get("type")=="text" and isinstance(t.get("text"),str)]
                    prompts[rid]=(idx,h("".join(texts)));continue
                if types[j]!="ObservationEvent" or (pred and (rid not in cap or step>cap[rid])) or (not pred and rid in futu and futu[rid]["idx"]<=idx):continue
                e=json.loads(bat.column("event_json")[j].as_py());obs=e.get("raw",{}).get("observation",{})
                if obs.get("kind")!="FileEditorObservation" or obs.get("command")!="view" or obs.get("is_error"):continue
                address=norm(obs.get("path"))
                if not address:continue
                text="\n".join(a["text"] for a in obs.get("content",[]) if isinstance(a,dict) and a.get("type")=="text" and isinstance(a.get("text"),str))
                if not any(HEADER.search(line) and norm(HEADER.search(line)[1])==address for line in text.splitlines()):continue
                rows=extract_lines(text);eout=dict(path=address,step=step,idx=idx,lines=rows)
                if pred:steps[rid].append(eout)
                else:futu[rid]=eout
    observations=[];targets=[];allmeta=[]
    for rid,run in runs.items():
        if run["role"]!="takeover":continue
        pair=(run["initial_run_id"],run["checkpoint_id"]);assert pair in ck
        receipt=native[rid];delivered=rid in prompts and prompts[rid][1]==receipt["sha"];seen["takeovers"]+=1;seen["verified_delivery"]+=delivered;seen["user_message_missing"]+=rid not in prompts
        if not delivered:continue
        group=[run[k] for k in ("initial_run_id","checkpoint_id","successor","subset","attempt")];cp=h("|".join(pair));q=h(rid);group=h("|".join(group));a=run["handoff_view"]
        if a!="repo_only":seen["non_repo_total"]+=1;seen["note_section_recognized"]+=bool(receipt["section"])
        else:assert not receipt["section"]
        allmeta.append(dict(q=q,cp=cp,issue=run["instance_id"],group=group,view=a,subset=run["subset"],sha=receipt["sha"],prompt_chars=receipt["prompt_chars"]))
        z=futu.get(rid,{})
        if len(z.get("lines",[]))>=2:target=[z["path"],z["lines"][0],z["lines"][-1]]
        else:target=None
        targets.append(dict(q=q,target=target,reason=("no_strict_view" if not z else "view_has_under_two_lines" if target is None else "eligible")))
    for (pred,c),cut in sorted(ck.items()):
        issue=runs[pred]["instance_id"];observations.append(dict(cp=h(pred+"|"+c),issue=issue,question=meta[issue]["problem_statement"],events=sorted([r for r in steps[pred] if r["step"]<=cut],key=lambda r:r["idx"])))
    secs={h(rid):o["section"] for rid,o in native.items() if h(rid) in {e["q"] for e in allmeta}}
    rec=dict(prefix=save(P/"prefix.json.gz",observations),targets=save(P/"targets.json.gz",targets),rendered_sections=save(P/"sections.json.gz",secs),public_meta=save(D/"delivery-metadata.json.gz",allmeta),n_checkpoints=len(observations),events=sum(map(len,steps.values())),flow=seen,protocol=sha(D/"PROTOCOL_RU.md"))
    save(D/"projection.json",rec);print(rec)
if __name__=="__main__":main()

