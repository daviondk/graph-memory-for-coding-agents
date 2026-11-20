"""Fixed public preset DEFLATE dictionary, learned only from unrelated SWE-smith training repos."""
from collections import Counter,defaultdict
import json,re
from shared import D,WORK,printed,rows,save,sha

def main():
    freq=Counter();repos=defaultdict(set);n=0;seenrepos=set()
    inputs=sorted((WORK/"memory_session5/packets/source/train").glob("*.gz"))
    for path in inputs:
        for task in rows(path):
            repo=task["instance"].partition(".")[0];seenrepos.add(repo);n+=1
            unique=set()
            for _,args,out in task["events"]:
                if args.get("command")!="view": continue
                for text in printed(out).values():
                    encoded=json.dumps(text,ensure_ascii=False,separators=(",",":")).encode("utf8")
                    if 3<=len(encoded)<=120: unique.add(encoded+b",")
                    for term in re.findall(rb"[A-Za-z_]\w{3,30}| {4,24}\w+|\b(?:def|class|if|from|import|return|raise|for) [A-Za-z_.]+",encoded):
                        unique.add(term)
            freq.update(unique)
            for term in unique:repos[term].add(repo)
    # zlib gives the tail of its 32 KiB preset dictionary the smallest offsets.
    ranked=sorted((t for t in freq if len(repos[t])>=3 and freq[t]>=4),key=lambda t:(freq[t]*min(28,len(t)),len(repos[t]),t),reverse=True)
    entries=[];used=0
    for term in ranked:
        if used+len(term)+1>32768: continue
        entries.append(term);used+=len(term)+1
    data=b"\n".join(reversed(entries));(D/"python_prior.bin").write_bytes(data)
    save(D/"dictionary_receipt.json",dict(sessions=n,projects=sorted(seenrepos),entries=len(entries),bytes=len(data),sha=sha(D/"python_prior.bin"),source={str(p):sha(p) for p in inputs}))
    print(n,len(seenrepos),len(data),len(entries))
if __name__=="__main__":main()
