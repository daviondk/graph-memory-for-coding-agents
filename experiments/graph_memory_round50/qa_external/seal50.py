"""Recover the final receipt from complete, ungraded outputs after the inherited client's path error."""
import json
from paths50 import *
def elapsed(text):
    m,s,ms,us=(int(x) for x in text.split("."))
    return 60*m+s+ms/1000+us/1e6
def main():
    check50()
    assert not (D50/"gold.json.gz").exists() and not (D50/"answer-seal.json").exists()
    src=get(D50/"input-seal.json");prompts=get(D50/"prompts.json.gz")
    answers=get(D50/"answers.json.gz");audit=get(D50/"replay.json")
    p=P50/("output-"+src["prompts"]+".jsonl")
    journal=[json.loads(line) for line in p.read_text(encoding="utf8").splitlines()]
    assert len(journal)==len(answers)==len(prompts)==src["unique"]
    assert dict(journal)==answers and [r[0] for r in journal]==sorted(prompts,key=lambda k:hexb(("r49-infer|"+k).encode()))
    assert set(audit)==set(sorted(prompts,key=lambda k:hexb(("r49-repeat|"+k).encode()))[:32])
    log=(P50/"server.stderr").read_text(encoding="utf8").splitlines()
    begin=[elapsed(s.split(" ")[0]) for s in log if "launch_slot_" in s]
    end=[elapsed(s.split(" ")[0]) for s in log if "stop processing: n_tokens" in s]
    assert len(begin)==len(end)==len(prompts)+32
    plan=get(W50/"graph_memory_round46/reader_transfer/plan.json")
    rec=dict(answers=sha(D50/"answers.json.gz"),audit=sha(D50/"replay.json"),input=sha(D50/"input-seal.json"),
       model=plan["model"],engine=plan["server"],inference=sha(R49/"generate.py"),client=sha(R49/"runtime.py"),props=plan["props"],
       unique=len(prompts),different=sum(v!=answers[k] for k,v in audit.items()),resumed=0,seconds=end[-1]-begin[0],
       timing_basis="first server task launch to last release, including intervening client work and repeats",
       receipt_recovered=True,recovery_code=sha(Path(__file__)),blind_log=sha(p),server_log=sha(P50/"server.stderr"))
    put(D50/"answer-seal.json",rec);print("sealed before grading",len(answers),len(audit),rec["different"],rec["seconds"])
if __name__=="__main__":main()
