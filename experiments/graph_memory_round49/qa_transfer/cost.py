"""Preserve a compact numeric log of the completed server requests."""
import re
from common import *

def main():
    sign=get(D/"answer-seal.json");assert sha(D/"answers.json.gz")==sign["answers"] and sign["resumed"]==0
    answers=get(D/"answers.json.gz");replay=get(D/"replay.json")
    order=sorted(answers,key=lambda k:hexb(("r49-infer|"+k).encode()))
    tests=sorted(replay,key=lambda k:hexb(("r49-repeat|"+k).encode()))
    raw=P/"server.stderr"
    pattern=re.compile(r"print_timing: id\s+\d+ \| task (\d+) \|\s+(prompt eval|eval|total) time =\s+([\d.]+) ms /\s+(\d+) tokens?")
    observed={};released=0;truncated=0
    for line in raw.open(encoding="utf8"):
        state=re.search(r"stop processing: n_tokens = \d+, truncated = (\d+)",line)
        if state:
            released+=1;truncated+=int(state[1])
        m=pattern.search(line)
        if m:
            tid,kind,ms,n=m.groups();t=observed.setdefault(int(tid),{})
            assert kind not in t;t[kind]=[float(ms),int(n)]
    assert len(observed)==released==len(order)+len(tests) and truncated==0
    rows=[]
    for j,(st,k) in enumerate(zip(observed,order+tests,strict=True)):
        sample=observed[st];assert sample.keys()=={"prompt eval","eval","total"}
        rows.append([k,int(j>=len(order)),*sample["prompt eval"],*sample["eval"],*sample["total"]])
    put(D/"timing-events.json.gz",rows)
    put(D/"costs.json",dict(columns=["prompt_hash","repeat","prefill_ms","prefill_tokens","decode_ms","decoded_tokens","total_ms","total_tokens"],
        events=len(rows),model_calls=len(order),repeats=len(tests),server_ms_sum=sum(x[6] for x in rows),
        prefill_ms_sum=sum(x[2] for x in rows),decode_ms_sum=sum(x[4] for x in rows),
        wall_seconds=sign["seconds"],raw_server_sha256=sha(raw),archive=sha(D/"timing-events.json.gz"),
        hardware=sha(D/"hardware.json"),outputs=sha(D/"answer-seal.json"),input_truncations=truncated,restart=False))
    print(len(rows),"server events")
if __name__=="__main__":main()
