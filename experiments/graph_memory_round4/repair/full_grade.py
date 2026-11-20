import gzip,json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from base import D,read,save,sha
from full_process import full_execute
from decide import rec

def main():
    assert all(sha((D/n).read_bytes())==h for n,h in read("choices_lock.json").items())
    raw={r["task_id"]:r for r in read("humanevalpack.json")}
    plus={r["entry_point"]:r for r in map(json.loads,gzip.open(D/"evalplus.jsonl.gz","rt",encoding="utf8"))}
    methods=read("per_task.json.gz");chosen=read("selected_candidates.json.gz");alternatives=read("alternatives.json.gz")
    assign=read("assign.json");past=read("past.json.gz");source={};targets=[]
    for t,s,c,a in zip(past,methods,chosen,alternatives,strict=True):
        i=t["id"];row=raw[i];name=t["name"];codes={}
        assert i==s["id"]==c["id"]==a["id"]
        def put(code):codes[sha(code)]=code;return sha(code)
        for k in assign[i].values():put(rec(t,k,"calls")["source"])
        for x in c["candidates"]:put(x["source"])
        for k in a["picks"].values():put(a["sources"][k])
        lookup={m:v["hash"] for m,v in s["methods"].items()}
        lookup["author"]=put(row["declaration"]+row["canonical_solution"])
        lookup["buggy"]=put(t["source"])
        assert set(lookup.values())<=codes.keys()
        for k in set(lookup.values()):
            source[i,k]=(name,codes[k])
        targets.append((i,lookup))
    jobs=[(i,k,test) for i,k in source for test in ("human","plus")]
    def grade(job):
        i,k,test=job;name,code=source[i,k]
        if not code:return {"status":"invalid"}
        suite=raw[i]["test"] if test=="human" else plus[name]["test"]
        return full_execute(dict(source=code,name=name,suite=suite,extra_call=test=="plus"))
    with ThreadPoolExecutor(4) as pool:rs=dict(zip(jobs,pool.map(grade,jobs)))
    out=[]
    for i,lookup in targets:
        out.append({"id":i,"tests":{test:{a:rs[i,k,test] for a,k in lookup.items()} for test in ("human","plus")}})
    save("full_suite_items.json.gz",out)
    total={}
    for test in ("human","plus"):
        valid=[x for x in out if x["tests"][test]["author"]["status"]=="pass" and x["tests"][test]["buggy"]["status"]!="pass"]
        total[test]={}
        for tag,group in [("all",out),("calibrated",valid)]:
            scores={a:dict(Counter(r["tests"][test][a]["status"] for r in group)) for a in out[0]["tests"][test]}
            total[test][tag]={"n":len(group),"scores":scores}
    save("full_results.json",{"unique_runs":len(jobs),"results":total});print(len(jobs),[(t,total[t]["calibrated"]["n"]) for t in total])
if __name__=="__main__":main()

