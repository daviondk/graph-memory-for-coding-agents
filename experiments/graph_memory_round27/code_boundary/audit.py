"""Recompute line-value observables from whole-source offsets, native events, and original diff hunks."""
from collections import Counter,defaultdict
from bisect import bisect_right
from itertools import accumulate
from statistics import mean
import io,re,struct,tokenize,warnings
import numpy as np
import pyarrow.parquet as pq
from tokenizers import Tokenizer
from common import *
def original_loc():
    f=next(Path("D:/CodexResearch/x20-r8-swerank-runtime").glob("locbench-test-*.parquet"))
    return pq.read_table(f,columns=["instance_id","patch"])
def changed(raw,path):
    chunk=re.split(r"(?m)^diff --git ",raw)
    file=next(x for x in chunk if x.startswith("a/"+path+" b/"+path+"\n") or x.startswith("a/"+path+" b/"+path+"\r\n"))
    pattern=re.compile(r"(?m)^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*(?:\n|$)")
    ans={}
    for match in pattern.finditer(file):
        i=int(match[1]);old=int(match[2] or 1);new=int(match[4] or 1)
        for l in file[match.end():].split("\n"):
            if old==0 and new==0:break
            if l.startswith("\\"):continue
            if l.startswith(" "):old-=1;new-=1;i+=1
            elif l.startswith("-"):
                if l[1:].strip():ans[i]=l[1:].rstrip("\r")
                old-=1;i+=1
            elif l.startswith("+"):new-=1
            else:break
        assert old==new==0,(old,new)
    return ans
def main():
    allcheck={}
    tok=Tokenizer.from_file(str(T));tok.no_truncation();tok.no_padding()
    originals={x["instance_id"]:x for x in map(json.loads,(P/"swe-explore.jsonl").open(encoding="utf8"))}
    dataset=original_loc();offset={x:i for i,x in enumerate(dataset["instance_id"].to_pylist())}
    for p in ("","loc-"):
        maps={x[0]:x for x in read(P/(p+"source-map.json"))};pred=read(D/(p+"forecasts.json.gz"));res=read(D/(p+"results.json"));receipt={r["id"]:r for r in read(D/(p+"per-case.json.gz"))}
        obs={x["id"]:x for x in read(D/(p+"observations.json.gz"))};checked=0;skips=[];stats=defaultdict(list);clipped=Counter();repeated=Counter();source_ids={}
        for f in pred:
            uid=f["id"];o=obs[uid];q=f["issue"];key=f["file"];_,repo,commit,path,rawsha,size=maps[key]
            blob=(P/"files"/key).read_bytes()
            assert hashlib.sha256(blob).hexdigest()==rawsha
            txt=io.TextIOWrapper(io.BytesIO(blob),encoding=tokenize.detect_encoding(io.BytesIO(blob).readline)[0],newline=None).read()
            enc=tok.encode(txt,add_special_tokens=False);ids=enc.ids
            beginnings=[0]+[x.end() for x in re.finditer("\n",txt)]
            byline=defaultdict(list)
            for j,(a,b) in enumerate(enc.offsets):
                one=bisect_right(beginnings,a);assert one==bisect_right(beginnings,b-1)
                byline[one].append(j)
            if p:
                original=changed(dataset["patch"][offset[q]].as_py(),path)
                source_lines=txt.split("\n")
                differences=[n for n,s in original.items() if n>len(source_lines) or s!=source_lines[n-1]]
                if differences:
                    assert uid not in receipt;skips.append([q,len(differences),len(original),uid]);continue
                target=set(original).intersection(byline)
            else:
                series=defaultdict(set)
                for r in originals[q]["read_step_info"][path]:
                    if r["traj_path"]==o["trajectory"]:series[r["step_idx"]].add((r["start"],r["end"]))
                first,second=sorted(series)[:2];assert first==o["step"] and len(series[second])==len(series[first])==1
                x,y=next(iter(series[first]));a,b=next(iter(series[second]))
                assert f["lines"]==[x,min(y,len(beginnings))]
                clipped["first"]+=y>len(beginnings);clipped["second"]+=b>len(beginnings)
                target={i for i in byline if a<=i<=b}
            assert target
            un={j for i in range(f["lines"][0],f["lines"][1]+1) for j in byline[i]}
            l,h=f["visible"];assert un==set(range(l,h))
            init={i for i in target if set(byline[i])<=un}
            m=receipt[uid];assert m["target_count"]==len(target) and m["initial"]==len(init)
            branch={}
            for branch_name,policies in (("",f["arms"]),("equal_",f["equal"])):
                for arm,v in policies.items():
                    k=branch_name+arm;returned=set();wire=[]
                    for a,b,anchor,nh,fee in v["windows"]:
                        header=tok.encode(f"[0:{anchor}]",add_special_tokens=False).ids;tokens=ids[a:b]
                        assert fee==len(tokens)+len(header) and nh==len(header)
                        returned.update(range(a,b));wire.extend(header);wire.extend(tokens)
                    assert hashlib.sha256(struct.pack("<"+"I"*len(wire),*wire)).hexdigest()==v["wire_sha"]
                    assert len(wire)==v["cost"]<=256;hits=sum(set(byline[i])<=un|returned for i in target);s=m["methods"][k]
                    assert hits==s["covered"] and len(wire)==s["tokens"] and abs(hits/len(target)-s["recall"])<1e-14
                    branch[k]=s["recall"];checked+=1
            stats[q].append(branch["equal_both"]-branch["equal_right"])
        v=np.array([mean(stats[q]) for q in sorted(stats)])
        rng=np.random.default_rng(27027)
        boot=np.array([rng.choice(v,size=len(v),replace=True).mean() for i in range(10000)])
        ci=np.percentile(boot,[2.5,97.5]);expected=res["contrasts"]["equal_both__equal_right"]
        assert abs(np.mean(v)-expected["mean"])<1e-12 and np.allclose(ci,expected["ci"],rtol=0,atol=1e-12)
        allcheck[p or "natural"]=dict(receipts=checked,rows=len(receipt),issues=len(v),independent_exclusions=skips,clipped=clipped,primary=expected["mean"],ci=list(ci),forecast_sha=sha(D/(p+"forecasts.json.gz")))
    save(D/"audit.json",allcheck);print(json.dumps(allcheck))
if __name__=="__main__":main()

