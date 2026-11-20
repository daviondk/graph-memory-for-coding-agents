import collections
import gzip
import json
import posixpath
import re
import shlex
from pathlib import Path

from harvest import D, get, save, sha

EXIT = re.compile(r"(?:exit(?:ed)?(?:\s+with)?(?:\s+(?:exit|return))?\s+code|return\s+code|exit\s+status)\s*[:=]?\s*([0-9]+)",re.I)
EMPTY = re.compile(r"Your (?:last )?command ran successfully and did not produce any output\.?",re.I)
COMMAND = re.compile(r"(?:^|[;&|\n])\s*(grep|rg|find|cat|ls|head|tail|sed|stat)\b")
ABSENT_EDITOR = re.compile(r"^The path (.+?) does not exist\. Please provide a valid path\.\s*$")
ABSENT_SHELL = re.compile(r"^(?:cat|ls|head|tail|sed|stat):\s*(?:cannot (?:access|open|read|stat)\s+)?[‘'\x22]?([^'‘’\x22\n]+?)[’'\x22]?(?: for reading)?: No such file or directory\.?\s*$")
FORBID = re.compile(r"[\x00\n\r;><\x60$&|]")
ID = re.compile(r"[A-Za-z0-9_./-]+")
def cleanpath(value,cwd):
    if not value or not ID.fullmatch(value) or not cwd:return None
    full=posixpath.normpath(posixpath.join(cwd,value))
    if full=="/testbed":return "."
    if not full.startswith("/testbed/"):return None
    return full[len("/testbed/"):]
def unique_id(note):
    return (note["iid"],json.dumps(note["key"],sort_keys=True))
def canon_search(cmd,cwd):
    if not isinstance(cmd,str):return None,"unknown_command",False
    cmd=cmd.strip()
    match=re.match(r"^cd (/[A-Za-z0-9_./-]+)\s*&&\s*(.+)$",cmd,re.S)
    if match:cwd,cmd=match.groups()
    head=re.search(r"\s*\|\s*head(?:\s+(?:-[0-9]+|-n\s+[0-9]+))?\s*$",cmd)
    suffix=bool(head)
    if head:cmd=cmd[:head.start()]
    if FORBID.search(cmd):return None,"compound_or_shell_expansion",suffix
    try:t=shlex.split(cmd)
    except ValueError:return None,"malformed_quote",suffix
    if not t:return None,"empty_command",suffix
    tool=t[0]
    if tool not in ("grep","rg","find","cat","ls","head","tail","sed","stat"):return None,"other_command",suffix
    if tool=="find":
        if len(t)<4 or t[2:] not in ([ "-name",t[-1]],["-type","f","-name",t[-1]],["-name",t[3],"-type","f"]):return None,"find_expression_or_wildcard",suffix
        target=t[t.index("-name")+1]
        scope=cleanpath(t[1],cwd)
        if not scope or "/" in target or not ID.fullmatch(target):return None,"find_expression_or_wildcard",suffix
        return {"kind":"name","literal":target,"scope":scope,"regular_only":"-type" in t},None,suffix
    if tool not in ("grep","rg"):
        arr=[(p,cleanpath(p,cwd)) for p in t[1:] if not p.startswith("-") and cleanpath(p,cwd)]
        return {"kind":"path_args","args":arr},None,suffix
    positional=[]; i=1; fixed=False; fold=False; word=False; filters=[]; recurse=tool=="rg"
    while i<len(t):
        x=t[i];i+=1
        if x in ("-A","-B","-C","-m"):
            if i>=len(t) or not t[i].isdigit():return None,"unsupported_option",suffix
            i+=1
        elif x.startswith("--include="):filters.append(x.partition("=")[2])
        elif x=="--include" or x=="-g":
            if i>=len(t):return None,"unsupported_option",suffix
            filters.append(t[i]);i+=1
        elif x=="-e":
            if i>=len(t) or positional:return None,"unsupported_option",suffix
            positional.append(t[i]);i+=1
        elif x in ("--","--line-number","--color=never"):pass
        elif x.startswith("-") and len(x)>1:
            flags=x[1:]
            if re.fullmatch(r"[ABCm]\d+",flags):continue
            if not re.fullmatch(r"[rRFniwhlHIE]+",flags):return None,"unsupported_option",suffix
            fixed|="F" in flags;fold|="i" in flags;word|="w" in flags;recurse|=bool(set(flags)&{"R","r"})
        else:positional.append(x)
    if not positional or len(positional)>2:return None,"missing_or_multiple_scopes",suffix
    if len(positional)==1 and tool=="grep" and not recurse:return None,"stdin_or_unknown_scope",suffix
    search=positional[0]
    if not fixed:
        literal=re.sub(r"\\([.])",r"\1",search)
        if re.search(r"(?<!\\)[.\[\]{}*+?^$|()\\]",search) or "\\" in literal:return None,"regex_or_complex_literal",suffix
    else:literal=search
    # Short UTF-8 literals with punctuation supported for fixed-string mode. Avoid fallback to a shell.
    if len(literal)<2 or len(literal)>160 or not literal.isascii():return None,"short_long_or_nonascii",suffix
    if any(not re.fullmatch(r"\*\.[A-Za-z0-9_]+",f) for f in filters):return None,"complex_include",suffix
    scope=cleanpath(positional[1] if len(positional)==2 else ".",cwd)
    if not scope:return None,"nonrepo_or_cwd",suffix
    return {"kind":"text","literal":literal,"scope":scope,"ignore_case":fold,"whole_word":word,"globs":sorted(filters),"recurse":recurse,"tool":tool},None,suffix

def classify(step):
    if not step:return None,"unaligned"
    args=step["args"]; tool=step["tool"].split(".")[-1]; raw=step["raw"]; seen=step["seen"];cwd=step["cwd"]
    if "editor" in tool and args.get("command")=="view":
        p=cleanpath(args.get("path",""),cwd)
        m=ABSENT_EDITOR.fullmatch(raw or "");v=ABSENT_EDITOR.search((seen or "").removeprefix("OBSERVATION:\n"))
        if m and v and p and cleanpath(m[1],cwd)==p and cleanpath(v[1],cwd)==p:return ("strict",{"kind":"path","literal":p,"scope":p},"editor_path_diagnostic"),None
        return None,"other_view"
    if tool!="bash":return None,"other_action"
    cmd=args.get("command","")
    if not COMMAND.search(cmd):return None,"other_action"
    k,why,suffix=canon_search(cmd,cwd)
    if not k:return None,why
    if raw is None or seen is None:return None,"ordinary_or_long_output"
    if k["kind"]=="path_args":
        m=ABSENT_SHELL.fullmatch(raw.strip())
        if m and "No such file or directory" in seen and not suffix:
            p=cleanpath(m[1],cwd)
            if p and p in [u for _,u in k["args"]]:return ("strict",{"kind":"path","literal":p,"scope":p},"shell_path_diagnostic"),None
        return None,"other_read"
    if re.search(r"No such file or directory|Permission denied|command not found|unmatched|unrecognized option|unknown option|Is a directory|not a directory|Invalid regular expression",raw+"\n"+seen,re.I):return None,"command_or_scope_error"
    codes={int(x) for x in EXIT.findall(raw+"\n"+seen)}
    if codes and codes not in ({0},{1}):return None,"unknown_or_error_exit"
    content=EXIT.sub("",raw).strip(" []()\n.:-")
    if content:return None,"ordinary_nonempty_output"
    if k["kind"]=="text" and codes=={1} and not suffix:return ("strict",k,"exit_1"),None
    if k["kind"]=="name" and codes=={0} and not suffix:return ("strict",k,"find_exit_0"),None
    if (not codes and not raw.strip() and EMPTY.fullmatch(seen.strip())) or suffix and codes in ({0},{1}):
        return ("weak",k,"head_no_hits" if suffix else "no_stdout_missing_numeric_exit"),None
    return None,"unconfirmed_empty_output"

def use(k,args):
    if not args:return False
    for key,val in args.items():
        if key=="command" and val in ("view","create","insert","str_replace","undo_edit"):continue
        if isinstance(val,str) and k["literal"] in val:return True
    return False
def main():
    counters=collections.defaultdict(collections.Counter); all_notes=[];population=get(D/"roster.json")
    for task in population:
        data=json.loads(gzip.decompress((D/"observations"/(task["iid"]+".json.gz")).read_bytes()));steps=data["steps"];counts=counters[task["panel"]]
        counts["all_actions"]+=len(steps)
        for j,step in enumerate(steps):
            found,why=classify(step)
            if not found:counts[why]+=1;continue
            tier,key,reason=found;counts[tier]+=1
            args=[x["args"] if x else {} for x in steps]
            all_notes.append({"iid":task["iid"],"panel":task["panel"],"repo":task["repo"],"base":task["base"],"step":j,"tier":tier,"key":key,"reason":reason,"input":step["args"],"raw":step["raw"],"shown":step["seen"],"cwd":step["cwd"],"use_next_three":any(use(key,x) for x in args[j+1:j+4]),"future_mention":any(use(key,x) for x in args[j+4:]),"future_exact_args":any(step["args"]==x for x in args[j+4:]),"n_future":len(steps)-1-j})
    save(D/"action_notes.json",all_notes)
    byid={}
    for z in all_notes:
        uid=unique_id(z)
        if uid not in byid or byid[uid]["tier"]=="weak" and z["tier"]=="strict":byid[uid]=z
    selected=[]
    for tier in ("strict","weak"):
        ids=sorted({v["iid"] for v in byid.values() if v["tier"]==tier},key=lambda i:sha(("r11-natural-neg-v1|"+i).encode()))[:24]
        selected.extend(v for v in byid.values() if v["tier"]==tier and v["iid"] in ids)
    save(D/"keys.json",selected);save(D/"coverage.json",counters)
    save(D/"key_lock.json",{"files":{p:sha((D/p).read_bytes()) for p in ["harvest.py","PROTOCOL_RU.md","ANNOTATION_RU.md","roster.json","roster_lock.json","receipts.json","classify.py","keys.json","action_notes.json","coverage.json"]},"unique_all":len(byid),"frozen_selection":len(selected),"totals":{tier:{'decisions':sum(v['tier']==tier for v in byid.values()),'tasks':len({v['iid'] for v in byid.values() if v['tier']==tier})} for tier in ['strict','weak']}})
    print(json.dumps({"counts":counters,"selection":get(D/"key_lock.json")["totals"],"eligible_instances":sorted({k["iid"] for k in selected})}))
if __name__=="__main__":main()
