"""Prepare a reference-blind held-out Java panel from the author's released ordinary retrieval."""
import re,json,sys,tarfile,hashlib
from pathlib import Path
from collections import Counter
import pyarrow.parquet as pq
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent/"reader"))
from evidence import trim,pp,cos,ignored,R4
from prepare5 import BAD
from data_io import files
import infer as storage
storage.D=D

def norm(s):
    return re.sub("[^a-z0-9]","",s.lower())
def banned_projects():
    names=set()
    for path in [*files("java","train"),*files("java","test"),*sorted((R4/"repo/archive_inputs").glob("*.parquet"))]:
        names.update(pq.read_table(path,columns=["repo_name"]).column(0).unique().to_pylist())
    return {norm(s) for s in names}
def candidates(row):return row["crossfile_context"]["list"][:5]
def relay(ctx,frags):
    order=list(range(len(frags))); evidence={}
    query=pp("\n".join(ctx.splitlines()[-10:]));whole=set(re.findall(r"[A-Za-z_$][\w$]*",ctx))
    for d,dest in enumerate(frags):
        typename=Path(dest["filename"]).stem
        token=re.compile(r"(?<![\w$])"+re.escape(typename)+r"(?![\w$])")
        best=(0.,-1,-1)
        for i,src in enumerate(frags):
            if i==d or src["filename"]==dest["filename"]: continue
            source_type=Path(src["filename"]).stem
            lines=src["retrieved_chunk"].splitlines()
            for j,line in enumerate(lines):
                if ignored(line) or not token.search(line):continue
                before=pp("\n".join(lines[max(0,j-3):j]));v=cos(before,query)
                if len(before&query)>=2 and v>=.40:
                    best=max(best,(v*(1+.5*(source_type in whole)),-i,-j))
        evidence[d]=best
    order.sort(key=lambda i:-evidence[i][0])
    return order,evidence
PREFIX="// Here are some relevant code fragments from other files of the repo:\n\n"
MARKER="// the below code fragment can be found in:"
def render(raw,fs,order):
    sections=raw.split(MARKER)
    if len(sections)==1+len(fs):
        return sections[0]+("\n\n".join(MARKER+sections[i+1].rstrip() for i in order))
    return PREFIX+"\n\n".join(MARKER+"\n// "+fs[i]["filename"]+"\n"+"\n".join("// "+s for s in fs[i]["retrieved_chunk"].splitlines()) for i in order)
def main():
    src=D/"crosscodeeval_data.tar.xz";name="java/line_completion_rg1_unixcoder_cosine_sim.jsonl"
    with tarfile.open(src) as t: data=[json.loads(s) for s in t.extractfile(name)]
    samples=[];seen=set();banned=banned_projects();counts=Counter()
    for row in sorted(data,key=lambda r:storage.sha("graph-r5-cross-java|"+r["metadata"]["task_id"])):
        meta=row["metadata"];repo=meta["repository"];ctx,ct=trim(row["prompt"],1536,True)
        if repo in seen:continue
        if norm(re.sub(r"-[0-9a-fA-F]{6,40}$","",repo)) in banned:counts["matched_excluded"]+=1;continue
        fs=candidates(row);raw=row["crossfile_context"]["text"]
        if not fs or BAD.search("\n".join([repo,meta["file"],ctx,raw])):counts["screened"]+=1;continue
        given=list(range(len(fs)));order,events=relay(ctx,fs)
        same=render(raw,fs,given);alt=render(raw,fs,order)
        snippets={"empty":("(no external fragment)",0),"official":trim(raw,512),"order":trim(same,512),"bridge":trim(alt,512)}
        samples.append(dict(id=meta["task_id"],repo=repo,ctx=ctx,ctx_tokens=ct,snippets=snippets,order=order,files=[f["filename"] for f in fs],observed_edge=events));seen.add(repo)
        if len(samples)>=96:break
    storage.save("D_packets.json.gz",samples)
    sources=["PROTOCOL_RU.md","prepare.py","infer_cross.py","D_packets.json.gz","eval_utils.py","eval_metric.py","java.txt","keywordlist.py"]
    storage.save("D_data_lock.json",dict(sha={n:storage.sha((D/n).read_bytes()) for n in sources},data_hash=storage.sha(src.read_bytes()),member=name,count_total=len(data),count_selected=len(samples),matched_repo_keys=len(banned),counts=counts,changed=sum(r["snippets"]["bridge"]!=r["snippets"]["order"] for r in samples),original_identical=sum(r["snippets"]["official"]==r["snippets"]["order"] for r in samples)))
    print(storage.read("D_data_lock.json"),flush=True)
if __name__=="__main__":main()

