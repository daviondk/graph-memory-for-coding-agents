"""Open only the reference next line after the final requests are sealed; pair the outcomes by repository."""
import re,sys
from collections import defaultdict
import numpy as np
from infer import D,read,save,sha
R=D.parent/"repo";sys.path.insert(0,str(R))
from data_io import rows,files
def first(s):
    lines=[z.strip() for z in s.splitlines() if z.strip()]
    if lines and lines[0].startswith("```"):lines=lines[1:]
    return next((z for z in lines if not z.startswith("```")),"")
def sim(s,t):
    if s==t:return 100
    prev=[0]*(len(t)+1)
    for c in s:
        cur=[0]
        for j,k in enumerate(t,1):
            cur.append(prev[j-1]+1 if c==k else max(prev[j],cur[-1]))
        prev=cur
    return round(200*prev[-1]/(len(s)+len(t))) if s or t else 100
def paired(items,a,b,field):
    groups=defaultdict(list)
    for row in items:
        groups[row["repo"]].append(row["methods"][a][field]-row["methods"][b][field])
    mat=np.array([(len(x),sum(x)) for x in groups.values()]);rng=np.random.default_rng(1811264)
    draws=rng.integers(len(mat),size=(10000,len(mat)));s=mat[draws].sum(axis=1)
    d=[x for g in groups.values() for x in g]
    return {"delta":float(np.mean(d)),"ci":np.quantile(s[:,1]/s[:,0],[.025,.975]).tolist(),"wins":sum(x>0 for x in d),"losses":sum(x<0 for x in d),"projects":len(groups)}
def main(key):
    assert all(sha((D/(key+"_calls")/n).read_bytes())==h for n,h in read(key+"_decisions.json").items())
    info=read(key+"_packets.json.gz");index=read(key+"_assignment.json");meta=defaultdict(dict)
    for x in info:meta[x["file"]][x["local_index"]]=x
    outs=[];calls={};identifier=re.compile(r"[A-Za-z_$][\w$]*")
    for path in files("java","test"):
        for j,raw in enumerate(rows(path,["next_line","gold_snippet_index"])):
            if j not in meta[path.name]:continue
            x=meta[path.name][j];ref=raw["next_line"].strip();arms={}
            for a,k in index[x["id"]].items():
                if k not in calls:calls[k]=read(key+"_calls/"+k+".json.gz")["reply"]
                msg=calls[k]["choices"][0]["message"].get("content") or "";p=first(msg)
                ids,gold=set(identifier.findall(p)),set(identifier.findall(ref))
                arms[a]={"generated":p,"em":int(p==ref),"es":sim(p,ref),"id_f1":(2*len(ids&gold)/(len(ids)+len(gold))) if ids or gold else 1.,
                         "retrieved":int(x["ranks"].get(a,-1)==raw["gold_snippet_index"]),"snippet_tokens":x["snippets"][a][1],"prompt_tokens":calls[k]["usage"]["prompt_tokens"]}
            outs.append({"id":x["id"],"repo":x["repo"],"panel":x["panel"],"gold":ref,"methods":arms,"different":index[x["id"]]["graph"]!=index[x["id"]]["semlith"]})
    assert len(outs)==len(info)
    def summary(sub):
        return {"n":len(sub),"methods":{a:{f:(sum(v) if f in ["em","retrieved"] else float(np.mean(v))) for f in ["em","es","id_f1","retrieved","prompt_tokens","snippet_tokens"] if (v:=[x["methods"][a][f] for x in sub])} for a in sub[0]["methods"]},
                "graph_minus_semlith":{f:paired(sub,"graph","semlith",f) for f in ("em","es","id_f1","retrieved")}}
    result={"all":summary(outs),"different":summary([x for x in outs if x["different"]]),"strata":{p:summary([x for x in outs if x["panel"]==p]) for p in set(x["panel"] for x in outs)},
       "physical_requests":len(calls),"prompt_tokens":sum(rec["usage"]["prompt_tokens"] for rec in calls.values()),"generated_tokens":sum(rec["usage"]["completion_tokens"] for rec in calls.values())}
    save(key+"_items.json.gz",outs);save(key+"_results.json",result)
    print(key,result["physical_requests"],result["all"])
if __name__=="__main__":main(sys.argv[1])

