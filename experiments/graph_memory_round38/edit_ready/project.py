"""Reduce already-signed benign traces to visible line facts and an isolated action grader."""
from common import *
import sys,importlib.util
sys.path.insert(0,str(ROOT/"graph_memory_round31/natural_handoff"))
from source import P,pq,REV
module_spec=importlib.util.spec_from_file_location("r37_projection",R37/"code_visibility/project.py")
project=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(project)
def make_target(ac,ob):
    raw=ac["action"];receipt=ob["observation"]
    old,new=raw.get("old_str"),raw.get("new_str")
    pre,post=receipt.get("old_content"),receipt.get("new_content")
    if not isinstance(old,str) or not old.strip():return {"reason":"empty_or_whitespace"}
    if not all(isinstance(x,str) for x in (new,pre,post)):return {"reason":"incomplete_native"}
    i=pre.find(old)
    if i<0 or pre.find(old,i+1)>=0 or pre[:i]+new+pre[i+len(old):]!=post:return {"reason":"nonunique_or_different"}
    if not (ac["id"]==ob["action_id"] and ac.get("tool_call_id")==ob.get("tool_call_id") and raw["path"]==receipt["path"]):return {"reason":"link_error"}
    # LF is the renderer separator; CR or exotic line breaks make exact row reconstruction ambiguous.
    if any(x in pre for x in ("\r","\v","\f","\x1c","\x1d","\x1e","\x85","\u2028","\u2029")):return {"reason":"unsupported_eol"}
    lines=pre.split("\n");start=pre.count("\n",0,i)+1
    first=i-(pre.rfind("\n",0,i)+1);cursor=first;atoms=[];num=start
    # Newline itself belongs to its preceding address. No following empty sentinel required.
    for piece in old.splitlines(keepends=True):
        eol=piece.endswith("\n");part=piece[:-1] if eol else piece
        assert lines[num-1][cursor:cursor+len(part)]==part
        atoms.append([num,h(lines[num-1]),int(eol)])
        num+=1;cursor=0
    return dict(reason="ok",path=h(project.norm(raw["path"])),atoms=atoms,old_bytes=len(old.encode()),partial_start=bool(first),partial_end=not old.endswith("\n") and i+len(old)<len(pre) and pre[i+len(old)]!="\n",leading_or_trailing_eol=old.startswith("\n") or old.endswith("\n"))
def main():
    corpus,b= open_r37(); lines,cs,rs,flow=timeline(corpus,b); del corpus,b
    save(D/"schedule.json.gz",lines)
    source=get(P/"files.json");ridmap={};lookup={};viewout={};targets={};pending={};obs_pending={};nviews=0
    for rid in lines:
        lookup[rid]={i:("view",i) for i in rs[rid]}
        for st,(end,addr) in cs[rid].items():lookup[rid][st]=("act",st);lookup[rid][end]=("obs",st)
    def bind(key,act,ob):
        val=make_target(act,ob);targets.setdefault(key[0],{})[key[1]]=val
    for n,ref in enumerate(source["events"]):
        file=P/ref["file"];assert sha(file)==ref["sha"]
        for batch in pq.ParquetFile(file).iter_batches(columns=["run_id","event_index","event_json"],batch_size=384):
            ids=batch.column("run_id").to_pylist();inds=batch.column("event_index").to_pylist()
            raws=batch.column("event_json")
            for k,(r,i) in enumerate(zip(ids,inds)):
                if r not in ridmap:ridmap[r]=h(r)
                rid=ridmap[r];sel=lookup.get(rid,{}).get(i)
                if sel is None:continue
                what,st=sel;key=(rid,st);raw=json.loads(raws[k].as_py())["raw"]
                if what=="view":
                    ob=raw["observation"];p,known,count=rs[rid][i]
                    assert project.norm(ob["path"])==p and ob["command"]=="view" and not ob["is_error"]
                    rows=project.numbered(project.textof(ob),ob["path"],False)
                    assert project.slots(rows)==known and len(rows)==count
                    viewout.setdefault(rid,{})[i]=[[a,h(s),len(s.encode()),int(a+1 in rows)] for a,s in sorted(rows.items())]
                    nviews+=1
                elif what=="act":
                    if key in obs_pending:bind(key,raw,obs_pending.pop(key))
                    else:pending[key]=raw
                elif key in pending:bind(key,pending.pop(key),raw)
                else:obs_pending[key]=raw
        if n%50==0:print(n,"views",nviews,"joined",sum(len(s) for s in targets.values()),flush=True)
    assert not pending and not obs_pending
    assert sum(len(t) for t in targets.values())==sum(len(t) for t in cs.values()) and nviews==sum(len(t) for t in rs.values())
    save(D/"visible.json.gz",viewout);save(D/"sealed-targets.json.gz",targets)
    save(D/"input-seal.json",dict(source_revision=REV,shards=len(source["events"]),flow=flow,visible_views=nviews,runs=len(lines),
        frozen_protocol=sha(D/"PROTOCOL_RU.md"),source_manifest=sha(P/"files.json"),
        artifacts={p:sha(D/p) for p in ("visible.json.gz","schedule.json.gz","sealed-targets.json.gz")}))
if __name__=="__main__":main()
