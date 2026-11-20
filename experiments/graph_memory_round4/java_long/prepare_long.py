"""Freeze a SHA-selected B subset, using only long prefix and external candidate data before decode."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
import sys

D=Path(__file__).resolve().parent
J=D.parent/"java_reader";R=D.parent/"repo"
sys.path.insert(0,str(J))
import prepare as b
import infer

def sha(x):return hashlib.sha256(x if isinstance(x,bytes) else x.encode()).hexdigest()
def save(name,x):
    p=D/name;s=json.dumps(x,ensure_ascii=True,separators=(",",":")).encode();p.write_bytes(gzip.compress(s,mtime=0) if p.suffix==".gz" else s)
def main():
    lock=json.loads((J/"B_data_lock.json").read_bytes());assert b.digest(J/"B_packets.json.gz")==lock["packets"]
    base=json.loads(gzip.decompress((J/"B_packets.json.gz").read_bytes()))
    candidates=collections.defaultdict(list);location={}
    for x in base:
        candidates[x["panel"]].append(x["id"]);location[(x["file"],x["local_index"])]=x
    ordered={p:sorted(lst,key=lambda i:sha("r4-java-long-prefix-30-v1|"+i)) for p,lst in candidates.items()}
    save("source_selection.json",{"rule":"SHA256(r4-java-long-prefix-30-v1|id)","initial":[i for v in sorted(ordered) for i in ordered[v][:24]],"queues":ordered,"protocol":b.digest(D/"PROTOCOL_RU.md")})
    ready={};excluded=[]
    for path in b.files("java","test"):
        assert b.digest(path)==lock["inputs"][path.name]
        for j,row in enumerate(b.rows(path,["code","context","gold_snippet_index","repo_name"])):
            xy=(path.name,j)
            if xy not in location:continue
            x=location[xy];i=x["id"]
            ctx,ct=b.trim("\n".join(row["code"].splitlines()[-30:]),1024,True)
            short,_=b.trim("\n".join(row["code"].splitlines()[-3:]),512,True)
            assert short==x["ctx"] and row["repo_name"]==x["repo"]
            rank=dict(x["ranks"]);rank["oracle"]=int(row["gold_snippet_index"])
            if not 0<=rank["oracle"]<len(row["context"]):raise ValueError(i)
            snippets={a:b.trim(row["context"][k],256) for a,k in rank.items()}
            assert all(list(snippets[a])==x["snippets"][a] for a in ("graph","semlith"))
            snippets["empty"]=("(no external fragment)",0)
            if b.BAD.search(" ".join([ctx,*[s[0] for s in snippets.values()]])):
                excluded.append(i);continue
            ready[i]=dict(x,ctx=ctx,ctx_tokens=ct,snippets=snippets,ranks=rank,short_ctx_tokens=x["ctx_tokens"])
    ids=[i for p in sorted(ordered) for i in [n for n in ordered[p] if n in ready][:24]]
    assert len(ids)==len(set(ids))==96
    items=[ready[i] for i in ids]
    save("long_packets.json.gz",items)
    save("long_data_lock.json",{"chosen":ids,"excluded_safety":excluded,"sources":lock["inputs"],"B_packets":lock["packets"],"prepare":b.digest(__file__),"selection":b.digest(D/"source_selection.json"),"tokenizer":b.digest(b.TOKENFILE),"protocol":b.digest(D/"PROTOCOL_RU.md"),"packets":b.digest(D/"long_packets.json.gz")})
    print(len(items),collections.Counter(z["panel"] for z in items),len(set(x["repo"] for x in items)),"repo")
if __name__=="__main__":main()
