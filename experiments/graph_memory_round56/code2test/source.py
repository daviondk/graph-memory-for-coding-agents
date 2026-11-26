"""Extract actor inputs, checking source checksums. The ranking pass never reads target columns."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import tarfile

HERE=Path(__file__).resolve().parent
EXP=HERE.parents[1]
R54=EXP/"graph_memory_round54/next_read"
R55=EXP/"graph_memory_round55/benchmark_history"
ARC=Path("D:/CodexResearch/x20-r54-trace-choice/agent_retrieval_bench.tar.zst")
OLD_CACHE=Path("D:/CodexResearch/x20-r55-edit-history")
SCRATCH=Path("D:/CodexResearch/x20-r56-code2test")
METHODS={"Qwen3-Embedding-4B":"embed4","Qwen3-Embedding-8B":"embed8","lexical_all_files":"lexical","repomap_all_files":"repomap",
         "pplx-embed-v1-4b":"pplx","nomic-embed-code":"nomic","jina-code-embeddings-0.5b":"jina"}

def read(path):
    b=path.read_bytes()
    return json.loads(gzip.decompress(b) if path.suffix==".gz" else b)

def save(path,obj):
    data=(json.dumps(obj,separators=(",",":"),sort_keys=True,ensure_ascii=True)+"\n").encode()
    path.write_bytes(gzip.compress(data,mtime=0) if path.suffix==".gz" else data)

def digest(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()

def roster():
    eligible=set(read(R54/"decisions.json.gz"))
    with tarfile.open(ARC,"r|zst") as arc:
        for m in arc:
            if m.name.endswith("/samples.jsonl"):
                rows={}
                for s in map(json.loads,arc.extractfile(m)):
                    if s["task_type"]!="code2test":continue
                    q=s["query"]
                    anchors=q["implementation_files"] if "implementation_files" in q else [q["changed_file"]]
                    assert all(isinstance(p,str) for p in anchors) and anchors
                    rows[s["id"]]={"repo":s["repo"],"base":s["base_commit"],"anchors":sorted(set(anchors)),
                                   "eligible":s["id"] in eligible}
                assert len(rows)==106 and sum(r["eligible"] for r in rows.values())==105
                return rows
    raise ValueError("Missing sample file")

def main():
    published=read(R54/"decision-seal.json")["sources"][ARC.name]
    assert digest(ARC)==published
    rows=roster()
    active={r["base"]:r["repo"] for r in rows.values()}
    catalog={};all_ranks={q:{} for q in rows}
    with tarfile.open(ARC,"r|zst") as tar:
        for m in tar:
            file=Path(m.name)
            if file.name.endswith(".chunks.jsonl"):
                base=file.name.split(".")[0]
                if base not in active:continue
                paths=set()
                for line in tar.extractfile(m):
                    chunk=json.loads(line)
                    assert chunk["base_commit"]==base and chunk["repo"]==active[base]
                    paths.add(chunk["path"])
                catalog[base]=sorted(paths)
            elif file.name.endswith("_details.jsonl"):
                model=METHODS.get(file.name.removesuffix("_details.jsonl"))
                if not model:continue
                for v in map(json.loads,tar.extractfile(m)):
                    q=v["sample_id"]
                    if q not in rows:continue
                    assert (v["base_commit"],v["repo"])==(rows[q]["base"],rows[q]["repo"])
                    assert v["candidate_filter"]=="all_files"
                    all_ranks[q][model]=v["top_files"][:20]
    assert set(catalog)==set(active)
    for q,r in rows.items():
        valid=set(catalog[r["base"]])
        assert set(all_ranks[q])==set(METHODS.values())
        assert all(set(seq)<=valid for seq in all_ranks[q].values())
    save(HERE/"roster.json",rows)
    save(HERE/"catalog.json.gz",catalog)
    save(HERE/"publisher.json.gz",all_ranks)
    full=sum(len(s) for s in catalog.values())
    seal=dict(archive=published,n=len(rows),eligible=105,bases=len(active),path_states=full,
              sources={n:digest(HERE/n) for n in ["source.py","PROTOCOL_RU.md","roster.json","catalog.json.gz","publisher.json.gz"]})
    save(HERE/"input-seal.json",seal)
    print(seal["bases"],full)
if __name__=="__main__":main()
