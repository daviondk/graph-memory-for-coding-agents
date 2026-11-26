"""Check the only capped answer, without changing the registered solver budget metrics."""
from grade import parse_answer
from isolation import execute
from generate import common,PARAMS,key
from study import *

def main():
    old=read("answers.json.gz");prompts=read("prompts.json.gz");refs=read("assignments.json.gz")
    limited=sorted(h for h,r in old.items() if r["stop"]=="limit")
    truncated=sorted(h for h,r in read("extra-answers.json.gz").items() if r["stop"]=="limit")
    assert truncated==limited and len(limited)==1
    eos=sorted(h for h,r in old.items() if r["stop"]=="eos")[:2]
    common.RUN=RAW;out={};jobs=[]
    with common.server(common.READER,["--parallel","1","--ctx-size","4096","--flash-attn","on","--threads","4"],"cap-reader",18956) as (url,s,hw):
        for h in eos+limited:
            resp=s.post(url+"/completion",json=dict(PARAMS,n_predict=1024,prompt=prompts[h]),timeout=120)
            resp.raise_for_status();v=resp.json();text=v["content"]
            out[h]=dict(text=text,tokens=v["tokens_predicted"],stop=v["stop_type"],byte_prefix=text.startswith(old[h]["text"]),
                        original_stop=old[h]["stop"],same_text=text==old[h]["text"])
            assert out[h]["byte_prefix"] and (h in limited or out[h]["same_text"])
    tasks=read("selections.json.gz")
    for q,arms in refs.items():
        for h in limited:
            if any(r["hash"]==h for r in arms.values()):
                t=tasks[q]["task"];code,status=parse_answer(out[h]["text"],t["name"])
                out[h]["status"]=status
                if code:jobs.append(dict(id=q+"|"+h,repo=t["repo"],path=t["path"],name=t["name"],kind="model",answer=code))
    # The primary runner disallows arbitrary imports in a generated implementation.
    # Run this specific, local package import in the same closed image as a sensitivity check.
    parse=read("execution.json.gz")["parse_status"]
    for k,mark in parse.items():
        if mark!="unsupported_import":continue
        q,h=k.rsplit("|",1);t=tasks[q]["task"]
        assert t["repo"]=="pytoolz/toolz" and t["name"]=="diff"
        txt=old[h]["text"];txt=txt.split("```python",1)[-1].split("```",1)[0].strip()
        tree=ast.parse(txt)
        assert len(tree.body)==1 and tree.body[0].name=="diff"
        assert all(x.module in {"collections","toolz"} for x in ast.walk(tree) if isinstance(x,ast.ImportFrom))
        assert all(x.module!="toolz" or [z.name for z in x.names]==["freq"] for x in ast.walk(tree) if isinstance(x,ast.ImportFrom))
        jobs.append(dict(id="package_import|"+k,repo=t["repo"],path=t["path"],name=t["name"],kind="model",answer=ast.unparse(tree)))
    results=execute(jobs)
    write("cap-and-import.json.gz",dict(max_tokens=1024,controls=eos,capped=limited,replay=out,tests=results,
                                       primary=digest((HERE/"results.json").read_bytes())))
    print("caps",[(k,r["stop"],r["tokens"],r["byte_prefix"]) for k,r in out.items()],"tests",results)
if __name__=="__main__":
    main()
