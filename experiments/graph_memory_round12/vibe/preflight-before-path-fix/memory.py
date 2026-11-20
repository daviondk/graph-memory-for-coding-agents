"""Implement two matched writers over official HistorySession inputs; score only from user query."""
import collections, hashlib, json, math, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]
RELEASE=Path("D:/CodexResearch/x20-official-vibe/VibeMemBench")
sys.path.insert(0,str(RELEASE/"scripts"))
from memory_interface import RetrievedMemory,MemorySystem
from tokenizers import Tokenizer
codec=Tokenizer.from_file(str(WORK/"memory_session5/live/tokenizer.json"))
FIELDS=["instance_id","repo","language","problem_statement","image_name","base_commit"]
IDS=["mpmath__mpmath-881","adamchainz__flake8-comprehensions-553"]
def trim(text,n):
    ids=codec.encode(text,add_special_tokens=False).ids
    return codec.decode(ids[:n],skip_special_tokens=False) if len(ids)>n else text
def words(text):return re.findall(r"[a-z][a-z0-9]+",text.lower())
def sha(data):return hashlib.sha256(data).hexdigest()
def save(name,x):(ROOT/name).write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
# Capture only simple read-only command lines and explicit pytest invocations; never execute them.
VIEW=re.compile(r"^(?:cat|sed|head|tail|grep|rg|find|nl|ls)\b")
TEST=re.compile(r"^(?:pytest|python(?:3)?\s+-m\s+pytest)\b")
PATH=re.compile(r"(?<![\w./])(?:[\w.-]+/)*[\w.-]+\.py\b")
def timeline(messages):
    calls={};events=[]
    for pos,m in enumerate(messages):
        for c in (m.get("tool_calls") or []):
            try:val=json.loads(c["function"]["arguments"]);cmd=val["command"].strip()
            except (KeyError,ValueError,TypeError,AttributeError):continue
            if len(cmd)>480 or any(z in cmd for z in ("\n",";","&&","$(",chr(96),">")):continue
            kind="test" if TEST.match(cmd) else "read" if VIEW.match(cmd) else ""
            if kind:calls[c["id"]]=(pos,kind,cmd)
        if m.get("role")!="tool" or m.get("tool_call_id") not in calls:continue
        p,kind,cmd=calls[m["tool_call_id"]]
        content=m.get("content","");extra=m.get("extra") or {}
        try:obj=json.loads(content);out=obj.get("output",content);status=obj.get("returncode",extra.get("returncode"))
        except (TypeError,ValueError):out=content;status=extra.get("returncode")
        if not isinstance(out,str):continue
        excerpt="\n".join(s[:260] for s in out.splitlines()[:8])
        paths=list(dict.fromkeys(PATH.findall(cmd+" "+excerpt)))[:6]
        events.append(dict(pos=p,kind=kind,cmd=cmd,out=excerpt,status=status,paths=paths))
    return events
class Memory(MemorySystem):
    def __init__(self,kind):self.kind=kind;self.docs=[]
    def add(self,session,*,scope):
        steps=timeline(session.messages)
        for i,step in enumerate(steps):
            if step["kind"]!="read" or not step["paths"]:continue
            test=next((x for x in steps[i+1:] if x["kind"]=="test" and x["pos"]-step["pos"]<=18),None)
            raw="Observed command: "+step["cmd"]+"\nOutput excerpt:\n"+step["out"]
            graph="Earlier observation: "+step["cmd"]+"\nPaths in that observation: "+", ".join(step["paths"])
            if test:
                graph+="\nSubsequent test command: "+test["cmd"]+"\nRecorded exit: "+str(test["status"] if test["status"] is not None else "unknown")
            else:graph+="\nNo subsequent test recorded within this window."
            terms=collections.Counter(words(raw))
            self.docs.append((scope.user_id,session.session_id,step["pos"],terms,raw,graph))
    def count(self):return len(self.docs)
    def search(self,query,*,scope,top_k):
        docs=[x for x in self.docs if x[0]==scope.user_id]
        if not docs:return []
        df=collections.Counter();avg=sum(sum(x[3].values()) for x in docs)/len(docs)
        for x in docs:df.update(x[3].keys())
        def score(x):
            tf=x[3];dl=sum(tf.values())
            return sum(math.log(1+(len(docs)-df[t]+.5)/(df[t]+.5))*tf[t]*2.2/(tf[t]+1.2*(.25+.75*dl/avg)) for t in set(words(query)) if tf[t])
        rank=sorted(docs,key=lambda d:(-score(d),d[1],d[2]))
        out=[];seen=set()
        for x in rank:
            if x[1] in seen:continue
            seen.add(x[1])
            out.append(RetrievedMemory(id=x[1]+":"+str(x[2]),content=trim(x[4 if self.kind=="raw" else 5],192),score=score(x),source_session_id=x[1]))
            if len(out)>=top_k:break
        return out
def prepare():
    import pyarrow.parquet as pq
    import run_memory as rm
    source=RELEASE/"benchmark/test.parquet"
    safe=pq.read_table(source,columns=FIELDS,filters=[("instance_id","in",IDS)])
    assert len(safe)==2
    (ROOT/"subset").mkdir(exist_ok=True)
    pq.write_table(safe,ROOT/"subset/test.parquet")
    save("cohort.json",dict(targets=safe.select([k for k in FIELDS if k!="problem_statement"]).to_pylist(),
       solver="Qwen3.8-27B-UD-Q4_K_M",seed=0,temperature=.5,steps=24,per_card=192,top_k=2))
    for target in rm.load_targets(filter_lang="python"):
        if target["instance_id"] not in IDS: continue
        for kind in ("raw","graph"):
            rm.run_one(target,method=kind,memory_factory=lambda:Memory(kind),top_k=2,out_root=ROOT/"memories",
                run_id="r12",max_session_mb=120,overwrite=False)
    files=[p for p in (ROOT/"memories").rglob("memory.txt")]
    assert len(files)==4 and all(p.stat().st_size for p in files)
    save("assignment-lock.json",{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in files+[ROOT/"PROTOCOL_RU.md",ROOT/"cohort.json",ROOT/"memory.py",ROOT/"subset/test.parquet"]})
if __name__=="__main__":prepare()
