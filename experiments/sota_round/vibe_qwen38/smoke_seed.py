"""Check paired seed routing and semantic replay from native server tool_calls."""
import json
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parent
message={"model":"qwen38-27b-ud-q4km","messages":[{"role":"system","content":"Use the bash tool to run the requested shell command."},
         {"role":"user","content":"Call bash once to run exactly printf REPLAY."}],"temperature":0.5,"max_tokens":128,
         "tools":[{"type":"function","function":{"name":"bash","description":"Run one shell command",
         "parameters":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}}}],
         "parallel_tool_calls":True}


def get(rep):
    payload=json.dumps(message).encode()
    url=f"http://127.0.0.1:18839/replicate/{rep}/v1/chat/completions"
    with urlopen(Request(url,data=payload,headers={"Content-Type":"application/json"}),timeout=120) as r:
        response=json.load(r)
    choice=response["choices"][0]
    call=choice["message"]["tool_calls"][0]
    assert call["id"] and choice["finish_reason"]=="tool_calls"
    assert call["function"]["name"]=="bash" and isinstance(call["function"]["arguments"],str)
    cmd=json.loads(call["function"]["arguments"])["command"]
    assert "REPLAY" in cmd
    return {"replicate":rep,"response_id":response["id"],"tool_id":call["id"],"command":cmd,"usage":response["usage"],
            "nonthinking_reason_chars": len(choice["message"].get("reasoning_content") or "")}


if __name__=="__main__":
    outs=[get(rep) for rep in [0,0,1]]
    assert outs[0]["command"]==outs[1]["command"]
    rows=[json.loads(s) for s in (ROOT/"requests.jsonl").read_text(encoding="utf8").splitlines()]
    by_response={r["id"]:r for r in rows if r.get("id")}
    routing=[by_response[o["response_id"]] for o in outs]
    assert routing[0]["seed"]==routing[1]["seed"]!=routing[2]["seed"]
    assert routing[0]["message_sha256"]==routing[1]["message_sha256"]==routing[2]["message_sha256"]
    for o,r in zip(outs,routing):
        assert o["nonthinking_reason_chars"]==0
        o["seed"]=r["seed"]
    (ROOT/"seed_smoke.json").write_text(json.dumps(outs,indent=2))
    print(json.dumps(outs,indent=2))
