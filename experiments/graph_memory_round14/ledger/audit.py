"""Recompute all empirical claims from preserved observations and upstream source snapshots."""
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import statistics

D=Path(__file__).resolve().parent
def load(name):
    b=(D/name).read_bytes()
    return json.loads(gzip.decompress(b) if name.endswith(".gz") else b)
def digest(b):return hashlib.sha256(b).hexdigest()
def text(receipt):
    return "\n".join(c["text"] for c in receipt["response"]["result"]["content"] if c["type"]=="text")
def decode(msg,old):
    # Separate reconstruction via map from new positions and removal of old positions.
    if msg.startswith("[unchanged since"):return old
    tokens=msg.splitlines()
    if not msg.startswith("[changed since"):
        return "".join(s.split("|",1)[1]+"\n" for s in tokens if re.match(r'^\d+:[0-9a-f]{2}\|',s)).encode()
    n=int(re.search(r", (\d+) lines now",tokens[0])[1])
    removed=set();added={}
    for s in tokens[1:]:
        if s.startswith("-"):
            start=int(re.match(r"^-(\d+):",s)[1])
            count=int(re.search(r"\((\d+) lines?\)",s)[1])
            removed.update(range(start,start+count))
        if s.startswith("+"):
            num,value=s.split("|",1);added[int(num.split(":")[0][1:])]=value
    remaining=iter(v for i,v in enumerate(old.decode().splitlines(),1) if i not in removed)
    new=[added[i] if i in added else next(remaining) for i in range(1,n+1)]
    assert next(remaining,None) is None
    return ("\n".join(new)+"\n").encode()
def statistics_for(rows):
    samples=[r["elapsed_ns"]/1000 for r in rows]
    return dict(n=len(rows),correct=sum(r["correct"] for r in rows),changed=sum(r["changed"] for r in rows),
                stale=sum(not r["correct"] and r["changed"] for r in rows),file_bytes=sum(r["file_payload_bytes"] for r in rows),
                response_bytes=sum(r["response_text_bytes"] for r in rows),cached=sum(r["cache_hit"] for r in rows),
                median_us=statistics.median(samples),sum_us=sum(samples))
def main():
    controlled=load("paired_metrics.json.gz");mutes=load("pair_states.json")
    state={s["case"]:s for s in mutes}
    calls=load("native_calls.json.gz");by=defaultdict(list)
    cases=Counter()
    subset=[]
    for b in calls:
        if b["phase"]!="repeat":continue
        case=f"{b['fixture']:02}/{b['scenario']}";s=state[case]
        original=(D/s["fixture"]).read_bytes();assert digest(original)==s["old_sha"]
        val=text(b)
        if b["policy"]=="native_range":ans=decode(val,b"");gold=s["new_range_sha"]
        else:ans=decode(val,original);gold=s["new_sha"]
        assert digest(ans)==gold,(case,b["policy"])
        subset.append((case,b["policy"]))
    assert len(set(subset))==len(subset)
    for r in controlled:
        gold=state[r["case"]]["new_sha" if r["scope"]=="whole" else "new_range_sha"]
        assert r["truth_sha"]==gold and r["correct"]==(r["actual_sha"]==gold)
        by[r["policy"]].append(r);cases[r["case"]]+=1
    assert len(cases)==96 and len(set(cases.values()))==1
    real=load("natural/released_pairs.json.gz");nc=load("natural/native_calls.json.gz")
    for r in nc:
        b=real[r["i"]];prior=b["old"].encode() if r["stage"]!="initial" else b""
        gold=b["sha_new"] if r["stage"]!="initial" else b["sha_old"]
        assert digest(decode(text(r),prior))==gold
    natural=defaultdict(list);repo=defaultdict(lambda:Counter())
    for r in load("natural/scores.json.gz"):
        pair=real[r["i"]];assert r["correct"]==(r["restored_sha"]==pair["sha_new"])
        natural[r["arm"]].append({"elapsed_ns":r["elapsed_ns"],"correct":r["correct"],"changed":r["changed"],
                                    "file_payload_bytes":r["payload"],"response_text_bytes":r["view_bytes"],"cache_hit":r["hit"]})
        if r["arm"]=="native":repo[r["repo"]]["with_file"]+=1;repo[r["repo"]]["changed"]+=r["changed"]
    out={"controlled":{a:statistics_for(b) for a,b in by.items()},
         "controlled_by_scenario":{c:{a:statistics_for([r for r in b if r["case"].split("/")[1]==c]) for a,b in by.items()} for c in sorted({s["scenario"] for s in mutes})},
         "natural":{a:statistics_for(b) for a,b in natural.items()},"natural_by_repository":dict(repo),
         "natural_missing":sum(r["new"] is None for r in real),"initial_cost":{"controlled":sum((D/s["fixture"]).stat().st_size for s in mutes),"natural":sum(len(r["old"].encode()) for r in real if r["new"] is not None)},
         "verified":{"native_control_followup":len(subset),"all_control_scores":len(controlled),"all_natural_scores":sum(map(len,natural.values())),"all_natural_mcp_calls":len(nc),"published_fixture_files":len(real)}}
    (D/"results.json").write_text(json.dumps(out,indent=1),encoding="utf8")
    print(json.dumps({"initial":out["initial_cost"],"natural_repos":out["natural_by_repository"],"validated":out["verified"]}))
if __name__=="__main__":main()
