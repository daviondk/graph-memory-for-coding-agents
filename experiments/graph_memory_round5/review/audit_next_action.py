"""Reconstruct and independently grade next-edit addresses from the raw H calls; match the primary per-task table."""
import collections
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
from audit_reader import HERE, check, check_files, digest, exact_discordants, read

WORK=HERE.parent/"next_action"

def parse(text):
    opening=text.find("{")
    if opening<0: return None
    try:
        d, _=json.JSONDecoder().raw_decode(text[opening:])
        path, number = d["path"],d["line"]
    except (KeyError,ValueError,TypeError):return None
    if not isinstance(path,str) or type(number)!=int or number<1:return None
    path=path.strip().replace(chr(92),"/")
    if path.startswith("/testbed/"): path=path[len("/testbed/"):]
    if path.startswith("./"):path=path[2:]
    return [path,number]


def classify(proposed, refpath, start):
    match=proposed is not None and proposed[0]==refpath
    return {"valid":int(proposed is not None),"file":int(match),"exact":int(match and proposed[1]==start),"near5":int(match and abs(proposed[1]-start)<=5)}


def main():
    while not (WORK/"H_decisions.json").is_file():time.sleep(4)
    dlock=read(WORK/"H_data_lock.json");check_files(WORK,dlock["sha"])
    check_files(WORK,read(WORK/"H_input_lock.json"))
    check(digest(HERE.parent/"action_probe/raw_pairs.jsonl.gz")==dlock["events"],"history-only upstream input digest")
    plan=read(WORK/"H_assignment.json"); manifest=read(WORK/"H_decisions.json");check_files(WORK/"H_calls",manifest)
    ids={cid for arms in plan.values() for cid in arms.values()}
    check({cid+".json.gz" for cid in ids}==set(manifest),"physical H calls")
    replies={}
    for cid in ids:
        record=read(WORK/"H_calls"/(cid+".json.gz")); req=record["request"]
        norm=json.dumps(req,separators=(",",":"),sort_keys=True,ensure_ascii=True).encode()
        check(hashlib.sha256(norm).hexdigest()==cid,"request hash")
        reply=record["reply"]; prediction=parse(reply["choices"][0]["message"].get("content") or "")
        replies[cid]=(req["messages"][-1]["content"],prediction,reply["usage"])
    reference_path=HERE.parent/"writer/headroom.jsonl.gz";refs={}
    with gzip.open(reference_path,"rt",encoding="utf8") as f:
        for values in map(json.loads,f):
            iid,cut,when,loc,start=values[:5]
            k=f"{iid}|{cut}"
            if k not in plan:continue
            check(k not in refs and cut<=when<cut+4 and start>=1,"reference timestamp or coordinate")
            refs[k]=(loc,start)
    packets=read(WORK/"H_packets.json.gz")
    check(set(refs)==set(plan)=={p["id"] for p in packets},"reference keys")
    check(len({r["instance"] for r in packets})==len(packets)==96 and len({r["repo"] for r in packets})==dlock["projects"],"H denominator")
    items={}; tot=collections.defaultdict(collections.Counter)
    for p in packets:
        k=p["id"]; loc,start=refs[k];arms={}
        for a,cid in plan[k].items():
            snip,n=p["snippets"][a];body,pred,usage=replies[cid]
            check(body=="Earlier observations:\n"+snip+"\n\nCurrent task and history:\n"+p["ctx"]+"\n\nPredict the next edit location.","H visible input")
            v=classify(pred,loc,start);tot[a].update(v);arms[a]=dict(v,proposed=pred,input_tokens=usage["prompt_tokens"],output_tokens=usage["completion_tokens"])
        v=classify(p["last_address"],loc,start);tot["last"].update(v);arms["last"]=dict(v,proposed=p["last_address"])
        items[k]={"ref":[loc,start],"arms":arms}
    rows={k:sum(r["arms"]["address"][k]-r["arms"]["terminal"][k] for r in items.values()) for k in ("file","near5","exact")}
    pair={}
    for name in ("file","near5","exact"):
        w=sum(r["arms"]["address"][name]>r["arms"]["terminal"][name] for r in items.values())
        l=sum(r["arms"]["address"][name]<r["arms"]["terminal"][name] for r in items.values())
        pair[name]={"wins":w,"losses":l,"delta_pp":100*(w-l)/len(items),"mcnemar_2s":exact_discordants(w,l)}
    while not (WORK/"H_items.json.gz").is_file():time.sleep(4)
    official=read(WORK/"H_items.json.gz");nfields=0
    check(len(official)==len(items),"H official item table")
    for p in official:
        z=items[p["id"]];check(z["ref"]==p["ref"],"H gold");nfields+=1
        for a,v in z["arms"].items():
            for field,value in v.items():
                check(value==p["m"][a][field],f"H {p['id']} {a} {field}")
                nfields+=1
    itemfile=HERE/"H_audit_items.json.gz"
    itemfile.write_bytes(gzip.compress(json.dumps(items,sort_keys=True,separators=(",",":")).encode(),mtime=0))
    out={"n":len(items),"projects":dlock["projects"],"changed_address_vs_terminal":sum(v["address"]!=v["terminal"] for v in plan.values()),"physical_calls":len(ids),
         "totals":tot,"address_vs_terminal":pair,"all_matching_fields":nfields,"primary_cells_verified":len(items)*3*2,
         "refs_sha":digest(reference_path),"official_table_sha":digest(WORK/"H_items.json.gz"),"independent_table_sha":digest(itemfile),"decision_sha":digest(WORK/"H_decisions.json"),"script_sha":digest(Path(__file__)),"utc":datetime.datetime.now(datetime.UTC).isoformat()}
    (HERE/"H_audit.json").write_text(json.dumps(out,indent=1),encoding="utf8");print(out)
if __name__=="__main__":main()
