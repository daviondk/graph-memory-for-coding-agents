"""Build state-local numeric features from the public inference export; never import labels."""
from pathlib import Path
from collections import Counter
from functools import lru_cache
import gzip,hashlib,json,os,re,sys
for v in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):os.environ[v]="1"
import numpy as np
from tokenizers import Tokenizer
HERE=Path(__file__).resolve().parent; WORK=HERE.parents[1]
OLD=WORK/"memory_session5/serbench"; PUB=OLD/"upstream/data/cal500"; sys.path.insert(0,str(OLD/"upstream/src"))
from serbench import baseline
ISE=WORK/"graph_memory_round33/budget_loss"; RANKPATH=WORK/"graph_memory_round20/factor_reader/hash64-weights.json"
WP=Path("D:/CodexResearch/x20-isetrace-runtime/e5-base-v2/tokenizer.json"); QW=OLD.parent/"packets/qwen_tokenizer.json"
SEC=re.compile(r"\b(cve[- ]?\d*|cwe[- ]?\d*|exploits?|exploiting|vulnerabilit\w*|security|injection|xss|csrf|rce|malware|pentest|sandbox escape|buffer overflow|heap overflow|use.after.free|denial.of.service|insecure deseriali[sz]ation|path traversal|privilege escalation|unsafe deseriali[sz]ation|remote code execution)\b",re.I)
PATH=re.compile(r"[\w@.+/\\-]+\.[A-Za-z][A-Za-z0-9_]*")
def norm(p):return str(p).replace(chr(92),"/").strip("./")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def rows(p):
    with gzip.open(p,"rt",encoding="utf8") as f:return [json.loads(s) for s in f]
def save(p,v):
    b=(json.dumps(v,separators=(",",":"),sort_keys=True)+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def paths(ev):
    text=json.dumps([ev.get("action_input"),ev.get("tool_output"),ev.get("opened_files")],ensure_ascii=False)
    return {norm(m.group()) for m in PATH.finditer(text)}
def ranks(v):
    ix=np.argsort(-np.asarray(v),kind="stable");return np.argsort(ix)+1
def main():
    raw=rows(PUB/"items.jsonl.gz");seen=sorted({r["instance_id"] for r in raw if SEC.search(str(r["issue"])+" "+str(r.get("information_need",""))+" "+r["repo"])})
    kept=[r for r in raw if r["instance_id"] not in seen]
    repos=sorted({r["repo"] for r in kept},key=lambda k:hashlib.sha256(("ser-cost-v1/"+k).encode()).digest())
    first=len(repos)*2//5;second=len(repos)*3//5
    repo_split={r:"train" if i<first else "dev" if i<second else "test" for i,r in enumerate(repos)}
    assert len({(r["repo"],r["instance_id"]) for r in kept})==len({r["instance_id"] for r in kept})
    tokenizers=[Tokenizer.from_file(str(p)) for p in (WP,QW)]
    for tk in tokenizers:tk.no_padding();tk.no_truncation()
    @lru_cache(None)
    def costs(path,txt):
        unit=path+"\n"+txt+"\n\n";return [len(t.encode(unit,add_special_tokens=False).ids) for t in tokenizers]
    d={r["state_id"]:r for r in rows(OLD/"dense_inputs.jsonl.gz")}; mat=np.load(OLD/"dense_vectors.npy",mmap_mode="r")
    sh=sha(OLD/"dense_vectors.npy"); assert sh==read(OLD/"dense_runtime.json")["vectors_sha256"]
    rank=read(RANKPATH)["rank"]; inputs={};counters=Counter();tracked=Counter()
    for r in kept:
        q=r["state_id"]; fr=d[q];s=repo_split[r["repo"]];cs=sorted(r["candidate_evidence"],key=lambda c:c["evidence_id"]);ids=[c["evidence_id"] for c in cs];look=dict(fr["candidates"])
        assert set(ids)==set(look) and len(ids)==len(set(ids))
        E=np.asarray(mat[[look[i] for i in ids]],dtype=np.float32); E/=np.linalg.norm(E,axis=1)[:,None]; dense=[]
        for k in ("state","addresses"):
            v=mat[fr["queries"][k]].astype(np.float32);v/=np.linalg.norm(v);dense.append(ranks(E@v))
        lexi=ranks(baseline._bm25_scores(baseline._query(r),[baseline._candidate_text(c) for c in cs]))
        assert [ids[i] for i in np.argsort(lexi)[:8]]==baseline.rank_row(r,8)
        rrf=ranks(1/(60+lexi)+1/(60+dense[0])+1/(60+dense[1]))
        n=len(cs);o=np.column_stack((-np.log(rrf),1/rrf,(n-rrf)/max(n-1,1)))@rank["coef"]+rank["intercept"]
        occ=[paths(e) for e in r["trajectory_prefix"]];adj=[]
        for c in cs:
            key=norm(c["source_path"]);hits=[j for j,z in enumerate(occ) if key in z]
            adj.append([len(hits),1/(len(occ)-hits[-1]) if hits else 0])
        wp,qw=np.array([costs(str(c.get("source_path") or ""),str(c.get("content_excerpt") or "")) for c in cs]).T
        a=np.array(adj);X=np.column_stack((np.log1p(rrf),np.log1p(wp),np.log1p(a[:,0]),a[:,1]))
        inputs[q]={"repo":r["repo"],"task":r["instance_id"],"split":s,"ids":ids,"wp":wp.tolist(),"qw":qw.tolist(),"x":X.tolist(),"off":o.tolist(),
                   "ranks":{"bm25":lexi.tolist(),"dense_state":dense[0].tolist(),"dense_addresses":dense[1].tolist(),"rrf":rrf.tolist()}}
        tracked[s]+=int(any(a[:,0]));counters[s]+=1
    dst=HERE/"features.json.gz";save(dst,inputs)
    save(HERE/"input.json",{"sources":{p.name:sha(p) for p in (PUB/"items.jsonl.gz",OLD/"dense_inputs.jsonl.gz",OLD/"dense_vectors.npy",WP,QW,RANKPATH,ISE/"models.json")},
        "features":sha(dst),"split_repos":repo_split,"split_counts":dict(counters),"states_with_path_edge":dict(tracked),"excluded_tasks":seen,
        "original":len(raw),"excluded_states":len(raw)-len(kept),"code":sha(Path(__file__)),"protocol":sha(HERE/"PROTOCOL_RU.md")})
    print(counters,tracked,"excluded",len(raw)-len(kept),flush=True)
if __name__=="__main__":main()
