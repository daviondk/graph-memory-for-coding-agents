"""Audit what source was returned, including repeated displays before editing."""
from pathlib import Path
from collections import Counter
import re,json,gzip,hashlib
from tokenizers import Tokenizer
D=Path(__file__).resolve().parent
PILOT=D.parent/"solver_pilot"
BASE=Path("D:/CodexResearch/x20-r38-traitlets-solver-export/repo")
MATCH=re.compile(r"^([^:\n|]+):(\d+) \| (.*)$")
QW=D.parents[1]/"memory_session5/packets/qwen_tokenizer.json"
def load(p):return json.loads(p.read_bytes())
def logs(name):
    return [json.loads(x) for x in gzip.decompress((PILOT/name).read_bytes()).splitlines()]
def source_lines(text,src):
    found=[]
    for line in text.splitlines():
        m=MATCH.fullmatch(line)
        if m:
            path,k,s=m[1],int(m[2]),m[3]
            if path in src and 1<=k<=len(src[path]) and src[path][k-1]==s:found.append((path,k))
    return found
def patch_spans(text,src):
    deleted=set();anchors=set()
    for line in text.splitlines():
        if line.startswith("--- a/"):
            path=line[6:]
        elif line.startswith("@@"):
            n=int(re.match(r"^@@ -(\d+)",line)[1])
        elif line.startswith("-") and not line.startswith("---"):
            deleted.add((path,n));n+=1
        elif line.startswith("+") and not line.startswith("+++"):
            anchors.update((path,j) for j in (n-1,n) if 1<=j<=len(src[path]))
        elif line.startswith(" "):
            n+=1
    return deleted,anchors
def main():
    plan=load(PILOT/"plan.json")
    src={p:(BASE/p).read_text(encoding="utf8",errors="replace").splitlines() for p in plan["base"]}
    for p,d in plan["base"].items():assert hashlib.sha256((BASE/p).read_bytes()).hexdigest()==d
    sc=set(k for r in logs("scout-log.jsonl.gz") for k in source_lines(r["output"],src))
    packets=load(PILOT/"packets.json")
    refs={(r["path"],i) for r in load(PILOT/"scout-selections.json") for i in range(r["lo"],r["hi"]+1)}
    assert refs<=sc
    tokenizer=Tokenizer.from_file(str(QW))
    result={}
    for c,arm in plan["roles"].items():
        packet=packets[c]["text"]
        transmitted=set(source_lines(packet,src))
        assert transmitted<=sc
        addressable=refs|transmitted if arm=="cards" else transmitted
        counts=Counter()
        for r in logs(c+"-log.jsonl.gz"):
            if r["action"]=="edit" and not r["output"].startswith("ERROR "):break
            if r["action"] in ("search","read"):counts.update(source_lines(r["output"],src))
        visited=set(counts)
        deleted,anchors=patch_spans((PILOT/(c+".diff")).read_text(encoding="utf8"),src)
        touched=deleted|anchors
        result[arm]=dict(shown=sum(counts.values()),unique=len(visited),repeat_displays=sum(counts.values())-len(counts),
            scout_intersection=len(visited&sc),addressable=len(addressable),retained_text_rows=len(transmitted),
            transmitted_then_reread=len(visited&transmitted),addressable_then_reread=len(visited&addressable),
            touched_old_or_adjacent=len(touched),touched_in_memory=len(touched&transmitted),touched_in_addressable=len(touched&addressable),
            touched_in_scout=len(touched&sc),touched_read_by_solver=len(touched&visited),qwen_tokens=len(tokenizer.encode(packet,add_special_tokens=False).ids))
    out=dict(arms=result,scout_unique=len(sc),refs=len(refs),tokenizer_sha=hashlib.sha256(QW.read_bytes()).hexdigest(),
             pilot_sha=hashlib.sha256((PILOT/"manifest.json").read_bytes()).hexdigest())
    (D/"results.json").write_bytes((json.dumps(out,indent=2,sort_keys=True)+"\n").encode())
    print(result)
if __name__=="__main__":main()

