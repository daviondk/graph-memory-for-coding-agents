"""Create two physical, allowlisted views -- actor and official evaluator -- at separate stages."""
from collections import defaultdict,Counter
from pathlib import Path
from compression import zstd
import ast,gzip,hashlib,json,re,tarfile
from download import S,REV
HERE=Path(__file__).resolve().parent
ARC=S/"agent_retrieval_bench_v2_edit2ripple.tar.zst"
SHA="a174196d69b531d176a65c76fea928b3f1c893710baa4efccc48e901ff404b2c"
R27=HERE.parents[1]/"graph_memory_round27/code_boundary/prepare.py"
def sha(b):return hashlib.sha256(b).hexdigest()
def idhash(s):return sha(s.encode())
def hashfile(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def save(path,data):
    b=(json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=True)+"\n").encode()
    path.write_bytes(gzip.compress(b,mtime=0) if path.suffix==".gz" else b)
def load(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def archive():
    return tarfile.open(ARC,"r|zst")
def risk():
    code=ast.parse(R27.read_text(encoding="utf-8-sig"));n,=[x for x in code.body if isinstance(x,ast.Assign) and getattr(x.targets[0],"id","")=="RISK"]
    scope={"re":re};exec(compile(ast.Module(body=[n],type_ignores=[]),str(R27),"exec"),scope);return scope["RISK"]
def changed(diff):
    return "\n".join(l[1:] for l in diff.splitlines() if l.startswith(("+","-")) and not l.startswith(("+++","---")))
def prepare():
    assert hashfile(ARC)==SHA;risk_rx=risk();keep={};excluded={};baseline={};total=0
    with archive() as t:
        for m in t:
            if m.name=="./benchmark/v2_edit2ripple/samples.jsonl":
                for line in t.extractfile(m):
                    r=json.loads(line)
                    v={k:r[k] for k in ("id","repo","base_commit")}
                    v.update({k:r["query"][k] for k in ("anchor_file","intent","anchor_diff")});total+=1
                    problem=" ".join([v["repo"],v["anchor_file"],v["intent"],changed(v["anchor_diff"])]).replace("_"," ")
                    if v["id"]=="8b6ab1ba0883ff8104d28524":excluded[v["id"]]="published_example"
                    elif risk_rx.search(problem):excluded[v["id"]]="outside_benign_scope"
                    else:keep[v["id"]]=v
            for name in ("bm25","repomap","lexical"):
                if m.name==f"./eval/v2_edit2ripple/{name}_details.jsonl":
                    out={}
                    for line in t.extractfile(m):
                        r=json.loads(line);q=r["sample_id"]
                        if q not in keep:continue
                        assert (r["repo"],r["base_commit"])==(keep[q]["repo"],keep[q]["base_commit"]) and r["candidate_filter"]=="all_files"
                        out[q]=r["top_files"]
                    baseline[name]=out
    assert len(keep)+len(excluded)==total==58 and all(set(v)==set(keep) for v in baseline.values())
    save(S/"actor-input.json.gz",keep);save(S/"author-top20.json.gz",baseline)
    save(HERE/"source.json",dict(total=total,eligible=len(keep),excluded=excluded,repo_counts=Counter(v["repo"] for v in keep.values()),
        archive=SHA,hf_revision=REV,query=hashfile(S/"actor-input.json.gz"),published_top=hashfile(S/"author-top20.json.gz"),
        protocol=hashfile(HERE/"PROTOCOL_RU.md"),policy=hashfile(R27),source=hashfile(Path(__file__))))
    print(total,len(keep),Counter(v["repo"] for v in keep.values()),Counter(excluded.values()))
if __name__=="__main__":prepare()

