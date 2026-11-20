from collections import defaultdict, Counter
from common import *
import requests

def main():
    CACHE.mkdir(exist_ok=True,parents=True)
    file=CACHE/"java-oracle.json"
    if not file.exists():
        r=requests.get(ORACLE,timeout=60);r.raise_for_status();file.write_bytes(r.content)
    pool=defaultdict(list)
    rejected=Counter()
    for c in json.loads(file.read_bytes()):
        proj=c["repository"].removeprefix("https://github.com/").removesuffix(".git")
        if proj not in PROJECTS:continue
        for ref in c["refactorings"]:
            kind,desc=ref["type"],ref["description"]
            if kind not in QUOTAS or ref["validation"]!="TP":continue
            if UNSAFE.search(desc):
                rejected["description_filter"]+=1;continue
            a,b=endpoints(kind,desc)
            if a is None or b is None:
                rejected["unparsed"]+=1;continue
            case=sha("|".join(["r9-forward-java",proj,c["sha1"],kind,desc]).encode())[:20]
            pool[proj,kind].append((case,c["sha1"],a,b))
    queries=[];labels={}
    for (project,kind),items in sorted(pool.items()):
        seen=Counter()
        ordered=[]
        for case,commit,source,dest in sorted(items):
            ordered.append((seen[commit],case,commit,source,dest));seen[commit]+=1
        for _,case,commit,source,dest in sorted(ordered)[:QUOTAS[kind]]:
            queries.append(dict(case=case,project=project,commit=commit,source=source))
            assert case not in labels
            labels[case]=dict(role=kind,target=dest)
    save("queries.json",queries);save("labels.json",labels)
    save("selection.json",dict(oracle=ORACLE,sha256=sha(file.read_bytes()),n=len(queries),commits=len({q['commit'] for q in queries}),
         excluded=dict(rejected),selected_role=Counter(t["role"] for t in labels.values()),
         files=hashfiles(["PROTOCOL_RU.md","common.py","select_cases.py","queries.json","labels.json"])))
    print(read("selection.json")["selected_role"],len(queries),len({q["commit"] for q in queries}))
if __name__=="__main__":main()
