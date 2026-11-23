"""Ensure the source identifier, bytes, ordering and cost exposed to the reader match assigned conditions."""
import json
from pathlib import Path
import reader as r

def main():
    parts={}
    for label,exp,local in (("different",r.ROOT,r.PRIVATE),("same",r.ROOT/"matched_controls",r.PRIVATE/"matched_controls")):
        lock=r.load(exp/"panel-lock.json");assert lock["private_payloads"]==r.pilot.sha(local/"payloads.json.gz")
        assert lock["panel"]==r.pilot.sha(exp/"panel.json.gz")
        payloads=r.load(local/"payloads.json.gz");panel=r.load(exp/"panel.json.gz")
        costs=[];counts=[];lengths=[];shared=[]
        for _,info in panel.items():
            datasets=[];questions=[]
            for arm,rec in info["arms"].items():
                key=rec["prompt_sha256"];p=payloads[key];assert r.h(r.stable(p))==key
                assert p["model"]==r.MODEL and p["tool_choice"]=="required"
                inp=json.loads(p["messages"][1]["content"])
                assert set(inp)=={"question","fragments"}
                questions.append(inp["question"]);visible=inp["fragments"]
                assert [z["id"] for z in visible]==[z["id"] for z in rec["fragments"]]
                hashes={z["id"]:r.h(z["text"].encode()) for z in visible}
                assert hashes=={z["id"]:z["text_sha256"] for z in rec["fragments"]}
                assert not r.excluded(inp["question"]) and not any(r.excluded(z["text"]) for z in visible)
                token_count=sum(z["token_count"] for z in rec["fragments"])
                assert token_count==rec["e5_tokens"]<=2048
                datasets.append(hashes);costs.append(token_count);counts.append(len(visible));lengths.append(len(r.stable(p)))
            a,b=datasets
            assert questions[0]==questions[1] and all(a[i]==b[i] for i in set(a)&set(b))
            assert (a==b)==(label=="same")
            shared.append(len(set(a)&set(b)))
        parts[label]={"unique_prompts":len(payloads),"question_pairs":len(panel),
                      "range_raw_prompt_bytes":[min(lengths),max(lengths)],"range_e5":[min(costs),max(costs)],
                      "range_visible_fragments":[min(counts),max(counts)],"shared_fragments_range":[min(shared),max(shared)]}
    r.save(r.ROOT/"input-check.json",parts)
    print(parts)
if __name__=="__main__":main()
