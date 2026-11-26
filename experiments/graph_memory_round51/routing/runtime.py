"""Local fixed Qwen inference following R47. Model generates text, never actions."""
from functools import lru_cache
import requests
from common import *
HOST=f"http://127.0.0.1:{PORT}"
client=requests.Session();client.trust_env=False
def call(route,body):
    rsp=client.post(HOST+route,json=body,timeout=120);rsp.raise_for_status();return rsp.json()
@lru_cache(maxsize=80000)
def enc(text,sp=False):return call("/tokenize",dict(content=text,parse_special=sp,add_special=False))["tokens"]
@lru_cache(maxsize=40000)
def dec(tokens):return call("/detokenize",dict(tokens=list(tokens)))["content"]
def generate(tokens):
    r=call("/completion",dict(prompt=tokens,temperature=0,top_k=1,seed=460001,n_predict=96,cache_prompt=False,
                              ignore_eos=False,stop=["\n"],stream=False))
    return dict(answer=r["content"].strip(),tokens=r["tokens_predicted"],stop=r["stop_type"])
def model_check():
    plan=get(R46/"plan.json")
    props=client.get(HOST+"/props",timeout=15).json()
    assert props["total_slots"]==1 and props["build_info"]==plan["props"]["build_info"]
    assert Path(props["model_path"])==MODEL and sha(MODEL)==plan["model"] and sha(SERVER)==plan["server"]
    assert hexb(props["chat_template"].encode())==plan["chat_template"]
    return {k:props[k] for k in ("build_info","model_ftype","total_slots")}
