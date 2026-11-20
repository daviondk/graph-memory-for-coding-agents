"""Freeze decisions from old code and update coordinates before evaluating the new graph."""
import difflib
import json
import sys
import warnings
from collections import Counter,defaultdict
from common import ROOT, POLICIES, modules, analyze, decode, answer, digest, dump

warnings.filterwarnings("ignore",category=SyntaxWarning)
def affected(rng,ops):
    lo,hi=rng
    for start,stop in ops:
        if start==stop:
            if lo-1<=start<=hi:return True
        elif start+1<=hi and lo<=stop:return True
    return False

def rows_for(project,old,new,paths_old,paths_new,stats):
    for filename,previous in sorted(paths_old.items()):
        current=paths_new.get(filename)
        if previous==current:continue
        stats["changed_or_deleted_modules"]+=1
        try:
            previous_lines=decode(previous).splitlines()
            functions=analyze(previous)
        except (UnicodeError,SyntaxError,KeyError,ValueError):
            stats["unreadable_old_modules"]+=1
            continue
        if not any(f["calls"] for f in functions.values()):continue
        has_map=current is not None
        if has_map:
            try:
                now=decode(current).splitlines()
            except (UnicodeError,SyntaxError):
                has_map=False
        if has_map:
            ops=[(a,b) for t,a,b,_,_ in difflib.SequenceMatcher(None,previous_lines,now,autojunk=True).get_opcodes() if t!="equal"]
        for name,f in functions.items():
            if not f["calls"]:continue
            reuse={k:False for k in POLICIES};reuse["always_reuse"]=True
            if has_map and not affected(f["full"],ops):
                reuse["caller"]=True
                reuse["dependencies"]=not any(affected(functions[c]["full"],ops) for c in f["calls"])
                reuse["headers"]=not any(affected(functions[c]["head"],ops) for c in f["calls"])
            yield dict(project=project,old=old["version"],new=new["version"],path=filename,caller=name,
                       old_answer=answer(functions,name),degree=len(f["calls"]),reuse=reuse)
def main():
    sources=json.loads((ROOT/"sources.json").read_bytes())
    series=defaultdict(list)
    for row in sources:series[row["project"]].append(row)
    stats=Counter()
    total=0
    with (ROOT/"decisions.jsonl").open("w",encoding="utf8",newline="\n") as out:
        for project,versions in series.items():
            before=modules(versions[0]["name"])
            for old,new in zip(versions,versions[1:]):
                after=modules(new["name"])
                for row in rows_for(project,old,new,before,after,stats):
                    out.write(json.dumps(row,separators=(",",":"))+"\n");total+=1
                before=after
    files=["PROTOCOL.md","sources.json","predict.py","common.py","score.py","decisions.jsonl"]
    dump("prediction-lock.json",dict(files={k:digest((ROOT/k).read_bytes()) for k in files},total=total,
                                    stats=dict(stats),python=sys.version))
    print("Frozen predictions:",total,dict(stats))
if __name__=="__main__":main()
