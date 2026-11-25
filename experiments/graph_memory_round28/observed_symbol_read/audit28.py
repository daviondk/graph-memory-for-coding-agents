"""Independent full-source token offsets, bounded unified hunk parser, paid response and permutation audits."""
from collections import Counter,defaultdict
from bisect import bisect_right
from itertools import accumulate
import io,re,struct,sys,tokenize
import numpy as np
import pyarrow.parquet as pq
from tokenizers import Tokenizer
from common28 import *
from prepare import prod
def old_deletions(patch):
    result={}
    for segment in re.split(r"(?m)^diff --git ",patch)[1:]:
        mt=re.search(r"(?m)^--- a/(.+)$",segment)
        if not mt:continue
        path=mt[1].strip()
        if not prod(path):continue
        expected={}
        for h in re.finditer(r"(?m)^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n",segment):
            i=int(h[1]);o=int(h[2] or 1);n=int(h[4] or 1)
            for ln in segment[h.end():].split("\n"):
                if o==n==0:break
                if ln.startswith("\\"):continue
                op=ln[:1]
                if op=="-":
                    if ln[1:].strip():expected[i]=ln[1:].rstrip("\r")
                    o-=1;i+=1
                elif op=="+":n-=1
                elif op==" ":o-=1;n-=1;i+=1
                else:break
            assert o==n==0
        if expected:result[path]=expected
    return result
def independent():
    tok=Tokenizer.from_file(str(T));tok.no_truncation();tok.no_padding()
    arms_all={};repo_sets={}
    for panel,ds in (("swe",V),("loc",B)):
        t=pq.read_table(ds,columns=["instance_id","patch"]);idx={q:i for i,q in enumerate(t["instance_id"].to_pylist())}
        inp={r["issue"]:r for r in read(D/(panel+"-inputs.json.gz"))};fx=read(D/(panel+"-forecasts.json.gz"))
        outcomes={r["issue"]:r for r in read(D/(panel+"-outcomes.json.gz"))};res=read(D/(panel+"-results.json"));counts=Counter();bad={};pair=[];ident=Counter();repo_sets[panel]={r["repo"].lower() for r in inp.values()}
        for f in fx:
            q=f["issue"];rr=inp[q];path=rr["path"]
            dataset=old_deletions(t["patch"][idx[q]].as_py());own=dataset.get(path,{});n=sum(map(len,dataset.values()))
            if not n:
                assert q in res["unscorable"];continue
            blob=(P/"files"/rr["file"]).read_bytes()
            assert hashlib.sha256(blob).hexdigest()==rr["sha"]
            txt=io.TextIOWrapper(io.BytesIO(blob),encoding=tokenize.detect_encoding(io.BytesIO(blob).readline)[0],newline=None).read()
            enc=tok.encode(txt,add_special_tokens=False);ind=[0]+[m.end() for m in re.finditer("\n",txt)];lineids=defaultdict(list)
            for i,(a,b) in enumerate(enc.offsets):
                line=bisect_right(ind,a);assert line==bisect_right(ind,b-1)
                lineids[line].append(i)
            lines=txt.split("\n")
            issues=[k for k,s in own.items() if k>len(lines) or lines[k-1]!=s or not lineids[k]]
            if issues:
                assert q in res["mismatch_or_unrepresented"];bad[q]=[len(issues),len(own)];continue
            g=outcomes[q];assert g["target"]==n and g["infile"]==len(own)
            lo,hi=f["first"];observed={j for k in range(lo,hi+1) for j in lineids[k]}
            assert observed==set(range(*f["visible"]))
            scores={}
            for kind,methods in (("",f["arms"]),("eq_",f["equal"])):
                for a,row in methods.items():
                    span=row["span"];v=set(range(*span)) if span else set()
                    head=tok.encode(f"[0:{span[0]}]",add_special_tokens=False).ids if span else []
                    payload=head+(enc.ids[span[0]:span[1]] if span else [])
                    assert len(payload)==row["cost"]<=256
                    assert hashlib.sha256(struct.pack("<"+"I"*len(payload),*payload)).hexdigest()==row["wire"]
                    covered=sum(set(lineids[k])<=v|observed for k in own);name=kind+a
                    m=g["out"][name];assert m["hit"]==covered and m["cost"]==len(payload)
                    counts["retokenized"]+=1;scores[name]=covered/n
            pair.append(scores["eq_query_call"]-scores["eq_repeat_bm25"])
            for k in ("literal","query_name","goto_first","call_unconditional","rewired","query_def"):
                ident[k+"_same_score"]+=scores[k]==scores["query_call"]
                ident[k+"_same_address"]+=f["address"][k]==f["address"]["query_call"]
        v=np.array(pair);rng=np.random.default_rng(28028)
        seq=[rng.choice(v,len(v)).mean() for i in range(10000)]
        r=res["contrasts"]["eq_query_call"]
        assert abs(np.mean(v)-r["mean"])<1e-12 and np.allclose(np.percentile(seq,[2.5,97.5]),r["ci"],rtol=0,atol=1e-12)
        assert len(pair)==res["scored"];arms_all[panel]=dict(verified=counts,scored=len(pair),sanity=dict(ident),exclusions=bad)
    r27=set()
    for p in ("","loc-"):
        r27.update(r["repo"].lower() for r in read(R/(p+"observations.json.gz")))
    assert not repo_sets["swe"]&repo_sets["loc"] and not (repo_sets["swe"]|repo_sets["loc"])&r27
    save(D/"audit.json",dict(panels=arms_all,disjoint_repos=True,previous_r27=sorted(r27)));print(arms_all)
if __name__=="__main__":independent()

