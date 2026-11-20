"""Exercise native bash calls, tool-result history, usage, finish reason and repeatable sampling."""
import argparse
import concurrent.futures
import json
import time
import urllib.request
from pathlib import Path


def post(endpoint,messages,**kwargs):
    obj=dict(model="Qwen/Qwen3-8B",messages=messages,temperature=.5,max_tokens=128,**kwargs)
    req=urllib.request.Request(endpoint+"/chat/completions",data=json.dumps(obj).encode(),
                               headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=180) as r:
        return json.load(r)


def main():
    args=argparse.ArgumentParser()
    args.add_argument("--root",default="http://127.0.0.1:18991")
    args.add_argument("--out",type=Path,required=True)
    a=args.parse_args()
    tool=dict(type="function",function=dict(name="bash",description="Execute a bash command",
              parameters=dict(type="object",properties={"command":{"type":"string"}},required=["command"])))
    messages=[dict(role="system",content="You are a shell assistant. Use the provided bash tool."),
              dict(role="user",content="Use bash to run exactly: printf VIBE_ENDPOINT_OK . Do not answer in prose.")]
    t=time.monotonic()
    def call():
        return post(a.root+"/replicate/0/v1",messages,tools=[tool],parallel_tool_calls=True)
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        first,duplicate=[f.result() for f in [pool.submit(call),pool.submit(call)]]
    ch=first["choices"][0]
    fc=ch["message"]["tool_calls"][0]
    assert ch["finish_reason"]=="tool_calls" and fc["function"]["name"]=="bash"
    assert "VIBE_ENDPOINT_OK" in json.loads(fc["function"]["arguments"])["command"]
    other=duplicate["choices"][0]["message"]["tool_calls"][0]
    assert fc["function"]==other["function"]
    assert first["usage"]["completion_tokens"]>0
    follow=post(a.root+"/replicate/0/v1",messages+[ch["message"],dict(role="tool",tool_call_id=fc["id"],
        content="VIBE_ENDPOINT_OK"),dict(role="user",content="Now reply with only CONFIRMED and no tool call.")])
    assert "CONFIRMED" in (follow["choices"][0]["message"]["content"] or "")
    out=dict(first=first,matched_duplicate=duplicate,follow=follow,seconds=time.monotonic()-t)
    a.out.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("verified",fc["function"],follow["choices"][0]["finish_reason"],out["seconds"],flush=True)


if __name__=="__main__":
    main()
