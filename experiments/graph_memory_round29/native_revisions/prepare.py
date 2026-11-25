"""Project versioned observations, lock connected groups, quarantine held-out labels."""
from collections import defaultdict
import hashlib
import re,string
from collections import Counter
from fetch import ROOT,read,save,checksum
def hashkey(s):return hashlib.sha256(s.encode()).hexdigest()
def normalize(text):return " ".join("".join(c for c in text.lower() if c not in string.punctuation).split())
def metrics(pred,gold):
    best=0
    a=normalize(pred).split()
    for t in gold:
        b=normalize(t).split();common=sum((Counter(a)&Counter(b)).values())
        best=max(best,2*common/(len(a)+len(b)) if common else 0)
    return [best,int(any(normalize(pred)==normalize(t) for t in gold))]
def views(name):
    return {str(q["id"]):([p["background"],p["situation"],q["question"]],[a["text"] for a in q["answers"]])
            for article in read(name)["data"] for p in article["paragraphs"] for q in p["qas"]}
def components(original,changed):
    parents={q:q for q in original};owners={}
    def leader(q):
        while q!=parents[q]:parents[q]=parents[parents[q]];q=parents[q]
        return q
    for q in sorted(original):
        for case in (original[q],changed[q]):
            for field,value in enumerate(case[0][:2]):
                key=(field," ".join(value.lower().split()));other=owners.setdefault(key,q)
                left,right=sorted([leader(q),leader(other)]);parents[right]=left
    return {q:leader(q) for q in original}
def main():
    original,changed=views("original"),views("edits")
    before,after=read("before"),read("after");assert original.keys()==changed.keys()==before.keys()==after.keys()
    clusters=components(original,changed);groups=sorted(set(clusters.values()),key=lambda g:hashkey("r29-ropes-learn-v1/"+g))
    training=set(groups[::2]);train={};observations={}
    for q in sorted(original):
        a,old_gold=original[q];b,new_gold=changed[q];cluster=clusters[q]
        observations[q]={"old":a,"new":b,"prediction":before[q],"group":cluster,"training":cluster in training}
        if cluster in training:train[q]=metrics(after[q],new_gold)[0]-metrics(before[q],new_gold)[0]
    from fetch import CACHE, REV
    import gzip,json
    folder=CACHE.parent/"projected";folder.mkdir(exist_ok=True)
    for name,obj in [("blind",observations),("training",train)]:
        (folder/(name+".json.gz")).write_bytes(gzip.compress(json.dumps(obj,sort_keys=True).encode(),mtime=0))
    save("inputs.json",{"protocol":checksum(ROOT/"PROTOCOL_RU.md"),"prepare":checksum(ROOT/"prepare.py"),"sources":checksum(ROOT/"sources.json"),
          "blind":checksum(folder/"blind.json.gz"),"training":checksum(folder/"training.json.gz"),"revision":REV,"n":len(clusters),
          "groups":len(groups),"training_groups":len(training),"train_n":len(train),"test_n":len(clusters)-len(train)})
if __name__=="__main__":main()
