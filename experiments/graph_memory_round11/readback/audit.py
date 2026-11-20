import collections,gzip,hashlib,json,random
from pathlib import Path
from replay import ROOT, sha, write
from prepare import WORK
P=ROOT/"probe"
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def main():
    sets={}
    for name,d in (("probe",P),("intervention",P/"intervention")):
        answers=load(d/"answers.json");calls={p.name.split(".")[0]:load(p) for p in (d/"calls").glob("*.json.gz")}
        assert set(calls)=={r.get("key") for r in answers}
        assert all(sha(json.dumps(c["request"],ensure_ascii=False,sort_keys=True,separators=(",",":")).encode())==k for k,c in calls.items())
        for a in answers:
            k=a["key"];content=calls[k]["response"]["choices"][0]["message"]["content"]
            normalized=content.strip().removeprefix(chr(96)*3+"json").removeprefix(chr(96)*3).removesuffix(chr(96)*3).strip()
            try: code=json.loads(normalized)["choice"]
            except (KeyError,TypeError,ValueError): code=None
            assert (code if type(code)==int and 1<=code<=4 else None)==a["choice"]
        sets[name]=dict(physical=len(calls),tokens=sum(c["response"]["usage"]["total_tokens"] for c in calls.values()),
            prompt=sum(c["response"]["usage"]["prompt_tokens"] for c in calls.values()),seconds=sum(t["elapsed"] for c in calls.values() for t in c["attempts"]))
    true=load(ROOT/"results.json");native=load(ROOT/"native-token-counts.json")
    assert all(true[p+"|8|visible"]["totals"]==x for p,x in native["counts"].items())
    rows=load(P/"intervention/rows.json");task=collections.defaultdict(list)
    for row in rows:task[row["id"].rsplit("|",1)[0]].append(row)
    diffs={k:sum(int(v["new_correct"])-int(v["no_alternate"]) for v in rr) for k,rr in task.items()}
    # Exact paired sign-flip for exchangeable target outcomes within a whole task.
    counts={0:1}
    for v in diffs.values():
        nxt=collections.Counter()
        for z,n in counts.items():nxt[z+v]+=n;nxt[z-v]+=n
        counts=nxt
    p=sum(n for k,n in counts.items() if abs(k)>=abs(sum(diffs.values())))/sum(counts.values())
    rng=random.Random(121);keys=list(task);boot=[]
    for i in range(10000):
        ss=rng.choices(keys,k=len(keys))
        boot.append(sum(diffs[k] for k in ss)/sum(len(task[k]) for k in ss))
    boot.sort()
    write("audit.json",dict(model_runs=sets,tokenizer_confirmed=native["rows"],task_count=len(task),
       counterfactual_archive_vs_hidden=dict(effect=sum(diffs.values())/len(rows),ci=[boot[249],boot[9749]],paired_task_sign_flip=p,
       project_count=len({k.split("__")[0] for k in task}))))
if __name__=="__main__":main()
