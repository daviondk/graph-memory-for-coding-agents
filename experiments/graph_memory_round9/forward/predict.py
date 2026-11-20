"""Freeze predictions from declared old identity and before/after Java artifacts. No label access."""
from collections import Counter,defaultdict
from common import *
from java_parse import *

def mapped(n,hs):
    shift=0
    for old,a,new,b in hs:
        if a and old<=n<old+a:return max(1,new+min(n-old,max(0,b-1)))
        if old+a<=n and (a or old<n):shift+=b-a
    return max(1,n+shift)

def rank(rec,q,prior,current,src,stats):
    changed=rec["files"][str(src["file_id"])]
    expected=changed["new"]
    hunks=changed["hunks"]
    span=[mapped(n,hunks) for n in range(src["start"],src["end"]+1)
          if not any(old<=n<old+a for old,a,_,b in hunks)]
    at=mapped(src["start"],hunks)
    counts=Counter(g for f in prior if f["path"]==src["path"] for g in f["grams"])
    hashes=set(sorted(src["grams"],key=lambda g:(counts[g],g))[:8])
    old=defaultdict(list);new=defaultdict(list)
    for i,f in enumerate(prior):old[methodkey(f)].append(i)
    for i,f in enumerate(current):new[methodkey(f)].append(i)
    missing=methodkey(src) not in new
    lost=[]
    call=(src["name"],len(src["types"]))
    for key,prev in old.items():
        if key==methodkey(src) or len(prev)!=1 or len(new[key])!=1:continue
        i,j=prev[0],new[key][0]
        if call in prior[i]["calls"] and call not in current[j]["calls"]:
            lost.append(j)
    def git_key(i):
        f=current[i];diff=f["path"]!=expected
        votes=0 if diff else sum(f["start"]<=n<=f["end"] for n in span)
        delta=10**9 if diff else abs(f["start"]-at)
        return (-votes,delta!=0,f["name"]!=src["name"],diff,f["owner"]!=src["owner"],delta,address(f))
    git=sorted(range(len(current)),key=git_key)
    lex=sorted(git,key=lambda i:-len(hashes&current[i]["grams"]))
    def first(order):return order[0] if order else None
    gi,li=first(git),first(lex)
    edge=bool(missing and lost)
    e=first([i for i in lex if i in lost]) if edge else li
    def preexisting(i):
        return bool(i is not None and missing and len(old[methodkey(current[i])])==1)
    roles=dict(disappear=missing,git_prior=preexisting(gi),lex_prior=preexisting(li),edge=edge,
               edge_lex_agree=bool(edge and li in lost))
    addr=dict(disappear=li,git_prior=gi,lex_prior=li,edge=e,edge_lex_agree=li)
    row=dict(case=q["case"],project=q["project"],commit=q["commit"],parent=rec["parent"],
             origin=address(src),roles=roles,addresses={k:address(current[i]) if i is not None else None for k,i in addr.items()},
             candidates=[address(m) for m in current],lost_callers=[address(current[j]) for j in lost],
             old_calls_seen=sum(call in m["calls"] for m in prior if methodkey(m)!=methodkey(src)),
             candidate_counts=[len(prior),len(current)],lexical_payload_bytes=8*len(hashes),
             selected_paths=len(rec["selected"][q["case"]]),**stats)
    return row

def main():
    sel=read("selection.json");check({k:v for k,v in sel["files"].items() if k!="labels.json"})
    src=read("sources.json.gz");check(read("acquisition.json")["files_sha"])
    preds=[];skip=[]
    for q in read("queries.json"):
        why=None;rec=src.get(q["commit"])
        if not rec:
            why="no_commit_frontier"
        else:
            group=project(rec,rec["selected"][q["case"]])
            if group is None:why="missing_source_blob"
            else:
                old,new,stats=group
                matches=locate(old,q["source"])
                if len(matches)!=1:why="old_matches_"+str(len(matches))
                else:preds.append(rank(rec,q,old,new,old[matches[0]],stats))
        if why:skip.append(dict(case=q["case"],project=q["project"],commit=q["commit"],reason=why))
    save("predictions.json.gz",preds);save("skips.json",skip)
    save("prediction-lock.json",hashfiles(["selection.json","queries.json","PROTOCOL_RU.md","acquisition.json","sources.json.gz",
        "common.py","java_parse.py","predict.py","predictions.json.gz","skips.json"]))
    print("predictions",len(preds),"skips",Counter(x["reason"] for x in skip))
if __name__=="__main__":main()
