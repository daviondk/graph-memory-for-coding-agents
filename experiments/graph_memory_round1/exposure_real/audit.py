"""Literal observational classifier; never executes corpus strings."""
import collections
import gzip
import hashlib
import json
import re
import shlex
import sys
from pathlib import Path

import pyarrow
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1]
OLD = WORK / "memory_session6/validity"
SHARDS = WORK / "memory_session5/packets/shards.json"
RAW = WORK / "memory_session4/compact/.scratch"
EXES = set("pydeps lint-imports import-linter grimp pyreverse modulegraph modulegraph2 pyan pyan3".split())
MODULES = set("pydeps importlinter import_linter grimp pyreverse pylint.pyreverse modulegraph modulegraph2 pyan pyan3".split())


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


def txt(m):
    x = m.get("content")
    return x if isinstance(x,str) else "\n".join(v.get("text","") for v in x or [] if isinstance(v,dict))


def events(messages):
    if any(m.get("role")=="tool" for m in messages):
        calls = {}
        for m in messages:
            if m.get("role")=="assistant":
                for call in m.get("tool_calls") or []:
                    f = call.get("function",{}); args = f.get("arguments") or {}
                    if isinstance(args,str):
                        try: args=json.loads(args)
                        except ValueError: continue
                    calls[call.get("id")] = (f.get("name"),args)
            elif m.get("role")=="tool":
                ids=m.get("tool_call_ids") or [m.get("tool_call_id")]
                if len(ids)==1 and ids[0] in calls:
                    yield *calls.pop(ids[0]), txt(m)
    else:
        last=None
        for m in messages:
            if m.get("role")=="assistant":
                fs=re.findall(r"<function=([\w.-]+)>(.*?)</function>",txt(m),re.S)
                last=None
                if len(fs)==1:
                    name,fields=fs[0];last=(name,{k:v.strip("\n") for k,v in re.findall(r"<parameter=([\w.-]+)>(.*?)</parameter>",fields,re.S)})
            elif m.get("role")=="user" and last:
                yield *last, txt(m)
                last=None


def segments(s):
    s=s.strip()
    if not s or "\n" in s or "\r" in s or "<<" in s or "$(" in s or "`" in s:
        return None
    try:
        lexer=shlex.shlex(s,posix=True,punctuation_chars=";&|")
        lexer.whitespace_split=True
        words=list(lexer)
    except ValueError:
        return None
    units=[]
    part=[]
    for token in words:
        if token in {"&&","||",";","|","&"}:
            if part: units.append(part)
            part=[]
        else:
            part.append(token)
    if part: units.append(part)
    return units


def find_search(args):
    i=0
    takes_arg={"-g","--glob","-t","--type","-T","--type-not","--include","--exclude","--exclude-dir",
               "-A","-B","-C","-m","--max-count","--max-depth","--color","--context","--before-context","--after-context"}
    switches={"--hidden","--fixed-strings","--line-number","--no-heading","--heading","--word-regexp",
              "--smart-case","--ignore-case","--no-ignore","--no-filename","--with-filename","--files-with-matches"}
    while i<len(args):
        arg=args[i]
        if arg in {"-e","--regexp","--"} and i+1<len(args):return args[i+1]
        if arg.startswith("--regexp="):return arg.split("=",1)[1]
        if arg.startswith("-e") and len(arg)>2:return arg[2:]
        if arg in takes_arg:i+=2;continue
        if arg in switches or re.fullmatch(r"-[rRniIwFElHPshv]+",arg) or re.fullmatch(r"-[ABCm]\d+",arg):i+=1;continue
        if arg.startswith("--") and "=" in arg:i+=1;continue
        if arg.startswith("-"):return None
        return arg
    return None


def classify(part):
    w=list(part)
    while w and re.fullmatch(r"[a-zA-Z_]\w*=.*",w[0]):w.pop(0)
    if w[:2] in (["uv","run"],["poetry","run"]):w=w[2:]
    if not w:return None
    exe=w[0].rsplit("/",1)[-1]
    if exe in EXES:return "graph",exe
    if re.fullmatch(r"python(?:\d+(?:\.\d+)?)?",exe) and len(w)>2 and w[1]=="-m":
        if any(w[2]==m or w[2].startswith(m+".") for m in MODULES):
            return "graph",w[2]
    if exe in {"rg","grep"} or (exe=="git" and w[1:2]==["grep"]):
        pattern=find_search(w[2:] if exe=="git" else w[1:])
        if pattern:
            pat=pattern.lstrip("^").strip()
            for prefix in (r"\s*",r"\s+",r"[ \t]*","[[:space:]]*"):
                if pat.startswith(prefix):
                    pat=pat[len(prefix):]
                    break
            if re.match(r"^(?:import|from)(?:\b|\\s)",pat):
                return "literal",digest(pat)


def analyze(messages):
    counts=collections.Counter(); findings=[]; edits=0; last={"graph":{}, "literal":{}}
    for tick,(name,arg,feedback) in enumerate(events(messages)):
        if not isinstance(arg,dict):continue
        if (name in ("str_replace_editor","str_replace_based_edit_tool","edit_file") and
            arg.get("command")=="str_replace" and re.search(r"(?:The file .*? has been edited\.|successfully replaced)",feedback[:1300],re.I)):
            edits+=1
        if name not in ("bash","execute_bash","run_command","terminal") or not isinstance(arg.get("command"),str):
            continue
        counts["shell"]+=1;cmd=arg["command"];parts=segments(cmd)
        if parts is None: continue
        counts["simple_shell"]+=1
        matched=collections.defaultdict(set)
        for part in parts:
            result=classify(part)
            if result:matched[result[0]].add(result[1])
        for kind,keys in matched.items():
            repeat=any(k in last[kind] for k in keys)
            after=any(k in last[kind] and edits>last[kind][k] for k in keys)
            counts[kind]+=1
            counts[kind+"_after_any_edit"]+=int(edits>0)
            counts[kind+"_repeat"]+=int(repeat)
            counts[kind+"_repeat_after_edit"]+=int(after)
            findings.append([tick,edits,kind,sorted(keys),digest(cmd)])
            for k in keys:last[kind][k]=edits
    counts["edits"]=edits
    counts["tasks"]=1
    for k in ["edits","graph","graph_after_any_edit","graph_repeat","graph_repeat_after_edit",
              "literal","literal_after_any_edit","literal_repeat","literal_repeat_after_edit"]:
        counts["tasks_"+k]=int(counts[k]>0)
    return counts,findings


def main():
    source_rows={}
    for line in gzip.open(OLD/"exposure.jsonl.gz","rt",encoding="utf-8"):
        r=json.loads(line);key=(r["shard"],r["row"]);assert key not in source_rows
        source_rows[key]=r
    totals=collections.Counter();byrepo=collections.defaultdict(collections.Counter)
    nshards=json.loads(SHARDS.read_text(encoding="utf-8-sig"))
    with gzip.open(HERE/"matches.jsonl.gz","wt",encoding="utf-8") as f:
        for k,desc in enumerate(nshards):
            file=RAW/Path(desc["path"]).name
            with file.open("rb") as stream: assert hashlib.file_digest(stream,"sha256").hexdigest()==desc["lfs"]["oid"]
            offset=0
            with pq.ParquetFile(file) as pf:
                for batch in pf.iter_batches(batch_size=32,columns=["messages"]):
                    for i in range(batch.num_rows):
                        r=source_rows.get((k,offset+i))
                        if not r:continue
                        body=batch[0][i].as_py();assert digest(body)==r["messages_sha"]
                        counts,findings=analyze(json.loads(body))
                        assert (counts["shell"],counts["edits"])==(r["shell_calls"],r["edits"])
                        totals.update(counts);byrepo[r["repo"]].update(counts)
                        if findings:
                            f.write(json.dumps({"repo":r["repo"],"issue":r["issue"],"shard":k,"row":offset+i,"matches":findings})+"\n")
                    offset+=batch.num_rows
    assert totals["tasks"]==len(source_rows)==4310
    output={"totals":totals,"byrepo":byrepo,"pyarrow":pyarrow.__version__,"python":sys.version,"sha256":{
        p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (HERE/"PROTOCOL.md",HERE/"audit.py",OLD/"exposure.jsonl.gz",SHARDS)}}
    (HERE/"results.json").write_text(json.dumps(output,indent=2),encoding="utf-8");print(json.dumps(totals))


if __name__=="__main__":main()
