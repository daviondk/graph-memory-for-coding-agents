"""Project public events to hashed addresses. No trajectory instruction is executed."""
from pathlib import Path
from hashlib import sha256
from collections import defaultdict,Counter
import sys,re,json
D=Path(__file__).resolve().parent
prior=D.parents[1]/"graph_memory_round31/natural_handoff"
sys.path.insert(0,str(prior))
from source import cohort,REV,P,sha,get,save,h,pq
from extract import norm,informative
num=re.compile(r"^ *([0-9]+)\t(.*)$")
def numbered(text,path,edit):
    marker=("on a snippet of " if edit else "on ")+path+":"
    vals={};active=False
    for line in text.splitlines():
        if "cat -n" in line and line.rstrip().endswith(marker):
            active=True
            continue
        m=num.fullmatch(line)
        if active and m:
            n=int(m[1]);s=m[2]
            if n in vals and vals[n]!=s:return {}
            # Extremely long lines may be visibly clipped by the tool host; skip their coordinate.
            if not re.search(r"<response clipped>|<NOTE:|\\.\\.\\.truncated",s,re.I):vals[n]=s
        elif active:
            active=False
    return vals

def locate(rows,new):
    if not rows or not new:return None
    groups=[];lst=[]
    for n,txt in sorted(rows.items()):
        if lst and n!=lst[-1][0]+1:groups.append(lst);lst=[]
        lst.append((n,txt))
    if lst:groups.append(lst)
    at=[]
    for group in groups:
        text="\n".join(s for _,s in group);i=text.find(new)
        while i!=-1:
            at.append(group[0][0]+text.count("\n",0,i))
            if len(at)>1:return None
            i=text.find(new,i+1)
    return at[0] if len(at)==1 else None

def slots(rows):return [[n,h(s)] for n,s in sorted(rows.items()) if informative(s)]
def textof(obs):return "\n".join(p["text"] for p in obs.get("content",[]) if isinstance(p,dict) and isinstance(p.get("text"),str))
def main():
    rr,meta=cohort(); acts={}; seq=defaultdict(list);wait={};flow=Counter(); refs=get(P/"files.json")["events"]
    index={rid:{"issue":x["instance_id"],"repo":meta[x["instance_id"]]["repo"],"subset":x["subset"],"role":x["role"]} for rid,x in rr.items()}
    def bind(tag,ac,e):
        j,obs,idx=e; path=norm(obs["path"]);rows=numbered(textof(obs),obs["path"],True)
        av=ac["action"];original=av.get("old_str");new=av.get("new_str")
        valid=bool(ac.get("idx",idx)>=0 and ac.get("idx",idx)<idx and isinstance(original,str) and isinstance(new,str) and original and norm(av.get("path"))==path and av.get("command")=="str_replace" and ac.get("id")==j.get("action_id") and ac.get("tool_call_id")==j.get("tool_call_id"))
        start=locate(rows,new) if valid else None
        edit={"k":start,"delta":new.count("\n")-original.count("\n") if valid else None,
              "old_breaks":original.count("\n") if valid else None,"rows":slots(rows),"visible":len(rows),"matched":valid,"action_index":ac.get("idx")}
        # Private-for-evaluation metadata cannot be reached by predictors. Store only numeric checks.
        before=obs.get("old_content");after=obs.get("new_content");audit={"native_full_verified":False,"native_anchor_agrees":None}
        if valid and isinstance(before,str) and isinstance(after,str):
            i=before.find(original)
            if i>=0 and before.find(original,i+1)<0 and before[:i]+new+before[i+len(original):]==after:
                n=1+before.count("\n",0,i);audit={"native_full_verified":True,"native_anchor_agrees":(n==start if start is not None else None)}
        seq[tag[0]].append((idx,"edit",path,edit,audit));flow["matched_edit_actions"]+=valid
    for ix,ref in enumerate(refs):
        path=P/ref["file"]; assert sha(path)==ref["sha"]
        tab=pq.ParquetFile(path)
        cols=["run_id","event_index","event_type","source_json_valid","event_json"]
        for b in tab.iter_batches(columns=cols,batch_size=512):
            ids=b.column("run_id").to_pylist();types=b.column("event_type").to_pylist();valid=b.column("source_json_valid").to_pylist();ixs=b.column("event_index").to_pylist()
            for i,(rid,typ) in enumerate(zip(ids,types)):
                if rid not in index or typ not in ("ObservationEvent","ActionEvent"):continue
                if not valid[i]:
                    seq[rid].append((ixs[i],"barrier"));flow["invalid_raw_event"]+=1;continue
                j=json.loads(b.column("event_json")[i].as_py()).get("raw",{});idx=ixs[i];flow["eligible_raw_events"]+=1
                if typ=="ActionEvent":
                    a=j.get("action",{});kind=a.get("kind")
                    if kind not in ("ThinkAction","FinishAction","FileEditorAction"):
                        seq[rid].append((idx,"barrier"));flow["barrier_"+str(kind)]+=1
                    if kind=="FileEditorAction" and a.get("command")!="view" and norm(a.get("path")):
                        seq[rid].append((idx,"write_start",norm(a["path"])))
                    if kind=="FileEditorAction" and a.get("command")=="str_replace" and norm(a.get("path")):
                        tag=(rid,j.get("id"));assert tag not in acts
                        if tag in wait:bind(tag,dict(j,idx=idx),wait.pop(tag))
                        else:acts[tag]={"action":a,"id":j.get("id"),"tool_call_id":j.get("tool_call_id"),"idx":idx}
                    continue
                obs=j.get("observation",{});kind=obs.get("kind")
                if kind not in ("ThinkObservation","FinishObservation","FileEditorObservation"):
                    seq[rid].append((idx,"barrier"));continue
                if kind!="FileEditorObservation" or obs.get("is_error"):continue
                pathkey=norm(obs.get("path"))
                if not pathkey:continue
                cmd=obs.get("command")
                if cmd=="view":
                    rows=numbered(textof(obs),obs["path"],False)
                    seq[rid].append((idx,"read",pathkey,slots(rows),len(rows)))
                elif cmd=="str_replace":
                    tag=(rid,j.get("action_id"));e=(j,obs,idx)
                    if tag in acts:bind(tag,acts.pop(tag),e)
                    else:wait[tag]=e
                else:seq[rid].append((idx,"other",pathkey))
        if ix%50==0:print(ix,len(refs),len(seq),flush=True)
    for (rid,_),(j,obs,idx) in wait.items():seq[rid].append((idx,"other",norm(obs["path"])))
    flow["unmatched_successful_edit"]=len(wait)
    out={}
    for rid,x in index.items():
        ev=sorted(seq[rid],key=lambda e:e[0]);assert len(ev)==len({e[0] for e in ev})
        out[h(rid)]=dict(**x,events=ev)
    dst=D/"events.json.gz";x=save(dst,out)
    save(D/"source-seal.json",dict(projection=x,code=sha(Path(__file__)),protocol=sha(D/"PROTOCOL_RU.md"),
        source_revision=REV,source_files=sha(P/"files.json"),cohort_source=sha(prior/"source.py"),revision_run_filter=sha(prior/"extract.py"),
        shards=len(refs),runs=len(out),flow=flow))
if __name__=="__main__":main()
