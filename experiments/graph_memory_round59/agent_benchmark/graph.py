"""Extract temporal incidences from addressed historical tool calls. No gold inputs."""
from collections import Counter, defaultdict, deque
import json
import re
from roster import HERE, OLD, STAGE, get, put, sha, safe_text

NAME=re.compile(r"\b[A-Za-z][A-Za-z_0-9]{2,55}\b")
SKIP=set("self None True False return import from class raise ValueError TypeError AssertionError Exception NotImplementedError".split())


def address(value):
    if not isinstance(value,str):
        return None
    p=value.replace("\\","/").split("/testbed/")
    if len(p)!=2:
        return None
    s=p[-1].strip("/")
    if not s or ".." in s.split("/") or not re.fullmatch(r"[A-Za-z0-9_./-]{1,165}",s):
        return None
    if not safe_text(s) or re.search(r"\b[a-z0-9_-]+__[a-z0-9_-]+-[0-9]{2,}\b|(?:^|/)\\.git/",s,re.I):
        return None
    return s


def extract(path):
    clock=0
    reads=deque()
    pair_counts=Counter()
    last={}
    ids=defaultdict(Counter)
    for line in path.read_bytes().splitlines():
        try:
            r=json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("type")!="assistant":
            continue
        content=r.get("message",{}).get("content")
        if not isinstance(content,list):
            continue
        for item in content:
            if item.get("type")!="tool_use":
                continue
            clock+=1
            while reads and clock-reads[0][0]>8:
                reads.popleft()
            name=item.get("name")
            args=item.get("input",{})
            if name not in ("Read","Edit","MultiEdit","Write") or not isinstance(args,dict):
                continue
            p=address(args.get("file_path"))
            if not p:
                continue
            if name=="Read":
                reads.append((clock,p))
                continue
            for a in {src for _,src in reads}:
                pair_counts[(a,p)]+=1
                last[(a,p)]=clock
            for change in args.get("edits",[args]):
                source=change.get("new_string",change.get("content",""))[:4500]
                words={w for w in NAME.findall(source) if w not in SKIP and safe_text(w)
                       and ("_" in w or re.search("[a-z][A-Z]",w) or w[0].isupper())}
                ids[p].update(words)
    top=sorted(pair_counts,key=lambda e:(-pair_counts[e],-last[e],e))[:6]
    src=sorted({a for a,b in top})
    dst=sorted({b for a,b in top})
    return dict(src=src,dst=dst,hints={p:[w for w,_ in sorted(ids[p].items(),key=lambda r:(-r[1],r[0]))[:4]] for p in dst},
                edges=[[src.index(a)+1,dst.index(b)+1] for a,b in top],counts=[pair_counts[e] for e in top],
                total_pairs=len(pair_counts),tool_calls=clock)


def main():
    c=get(HERE/"cohort.json.gz")
    idx={k:extract(STAGE/"traces"/(k+".jsonl")) for k in c["trace_keys"]}
    put("graph.json.gz",idx)
    put("graph-seal.json",dict(protocol=sha(HERE/"PROTOCOL_RU.md"),cohort=sha(HERE/"cohort.json.gz"),graph=sha(HERE/"graph.json.gz"),
        extractor=sha(HERE/"graph.py"),original_cards=sha(OLD/"cards.json"),
        library=sha(OLD/"evaluation_library.csv"),traces={k:sha(STAGE/"traces"/(k+".jsonl")) for k in idx}))
    print("Graph",len(idx),"historical sessions,",sum(len(r["edges"]) for r in idx.values()),"retained distinct pairs")

if __name__=="__main__":main()
