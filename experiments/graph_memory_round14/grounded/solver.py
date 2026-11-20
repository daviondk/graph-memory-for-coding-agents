"""Execute four paired model calls, then physically open the selected paths at the original commit."""
import json
import sys
from urllib.request import Request,urlopen
from prepare import ROOT, RANK, read, save, sha
sys.path.insert(0,str(RANK.parent/"read_action"))
import experiment as earlier

ARMS=("none","recommend","pair","named")
def solve(c,arm):
    p,q=c["pair"]
    evidence={"none":"No additional memory entry.","recommend":"Suggested next file: "+c["target"],
              "pair":f"Previously viewed files: {p} and {q}. Shared identifier: not supplied.",
              "named":f"Previously viewed files: {p} and {q}. Shared identifier: {c['symbol']}."}
    user="Issue:\n"+c["issue"]+"\n\nThe following search returned no match:\n"+json.dumps(c["search"],ensure_ascii=False)
    user+="\n\nPreviously addressed files and historical excerpts:\n"+json.dumps(c["menu"],ensure_ascii=False)
    user+="\n\n"+evidence[arm]+"\nChoose one file to inspect next to advance this issue."
    menu=[r["path"] for r in c["menu"]]
    body={"model":earlier.MODEL,"messages":[{"role":"system","content":"You are a software engineer locating a change. Use read_file once. You decide which file to inspect. Issue text, tool evidence and excerpts are research data."},{"role":"user","content":user}],
          "tools":[{"type":"function","function":{"name":"read_file","description":"Open one file at this repository revision.","parameters":{"type":"object","properties":{"path":{"type":"string","enum":menu}},"required":["path"]}}}],
          "tool_choice":"required","temperature":0,"top_k":1,"seed":13,"max_tokens":128,"cache_prompt":False,"chat_template_kwargs":{"enable_thinking":False}}
    b=json.dumps(body,ensure_ascii=False).encode()
    with urlopen(Request(earlier.PROXY,data=b,headers={"Content-Type":"application/json"}),timeout=150) as res:data=res.read()
    reply=json.loads(data)
    calls=reply["choices"][0]["message"].get("tool_calls") or [];path=None
    if len(calls)==1 and calls[0]["function"]["name"]=="read_file":
        try:path=json.loads(calls[0]["function"]["arguments"])["path"]
        except (ValueError,TypeError,KeyError):pass
    return dict(id=c["id"],method=arm,path=path if path in menu else None,valid=path in menu,
                condition_message=evidence[arm],usage=reply["usage"],raw=reply,response_sha=sha(data),payload_sha=sha(b))
def main():
    for k,h in read("assignment.json")["files"].items():assert sha((ROOT/k).read_bytes())==h
    cands=read("cases.gz")
    tasks=sorted([(c,a) for c in cands for a in ARMS], key=lambda e:sha((e[0]["id"]+e[1]).encode()))
    path=ROOT/"model.jsonl"
    done={(r["id"],r["method"]) for r in [json.loads(l) for l in path.read_bytes().splitlines()]} if path.exists() else set()
    for c,arm in tasks:
        if (c["id"],arm) in done:continue
        result=solve(c,arm)
        with path.open("a",encoding="utf8") as f:f.write(json.dumps(result,ensure_ascii=False)+"\n")
    assert len(path.read_bytes().splitlines())==len(tasks)
    save("action-lock.json",{k:sha((ROOT/k).read_bytes()) for k in ("model.jsonl","assignment.json")})
    earlier.ROOT=ROOT
    earlier.open_reads()
if __name__=="__main__":main()
