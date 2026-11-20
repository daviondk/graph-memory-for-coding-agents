"""Exact token accounting, including malformed outputs omitted by mini-SWE-agent trajectories."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path

from jinja2.sandbox import ImmutableSandboxedEnvironment


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--episodes",type=Path,required=True)
    cli.add_argument("--model",type=Path,required=True)
    cli.add_argument("--repo",type=Path,required=True)
    cli.add_argument("--runtime",type=Path,required=True)
    cli.add_argument("--out",type=Path,required=True)
    args=cli.parse_args()
    # Reproduce the pinned tokenizer's plain Jinja branch for this concrete template.
    env=ImmutableSandboxedEnvironment(trim_blocks=True,lstrip_blocks=True,extensions=["jinja2.ext.loopcontrols"])
    env.filters["tojson"]=lambda obj,**kw:json.dumps(obj,ensure_ascii=False,**kw)
    tpl=env.from_string(json.loads((args.model/"tokenizer_config.json").read_text("utf-8"))["chat_template"])
    import ast
    tool_file=args.repo/"mini-swe-agent/src/minisweagent/models/utils/actions_toolcall.py"
    mod=ast.parse(tool_file.read_text("utf-8"))
    tools=[ast.literal_eval(next(n.value for n in mod.body if isinstance(n,ast.Assign) and getattr(n.targets[0],"id","")=="BASH_TOOL"))]
    receipts=[json.loads(l) for l in (args.runtime/"requests.jsonl").read_text("utf-8").splitlines()]
    assert len({r["id"] for r in receipts})==len(receipts)
    mapped=[]
    for p in sorted(args.episodes.rglob("result.json")):
        if p.parent.name!="seed0":
            continue
        res=json.loads(p.read_text("utf-8"))
        if res["status"]!="ok":
            continue
        traj=json.loads((p.parent/(res["instance_id"]+".traj.json")).read_text("utf-8"))
        msg=traj["messages"]
        episode=[]
        for i,m in enumerate(msg):
            fmt=m.get("extra",{}).get("interrupt_type")=="FormatError"
            if m["role"]!="assistant" and not fmt:
                continue
            rendered=tpl.render(messages=msg[:i],tools=tools,add_generation_prompt=True,enable_thinking=False)
            h=hashlib.sha256(rendered.encode()).hexdigest()
            hits=[r for r in receipts if res["start_ts"]<=r["epoch"]<=res["end_ts"] and r["prompt_sha256"]==h]
            assert len(hits)==1, (res["instance_id"],res["method"],i,h,[r["id"] for r in hits],m.get("extra",{}).get("response",{}).get("id"))
            r=hits[0]
            if not fmt:
                assert m["extra"]["response"]["id"]==r["id"]
                assert m["extra"]["response"]["usage"]["prompt_tokens"]==r["usage"]["prompt_tokens"]
                assert m["extra"]["response"]["usage"]["completion_tokens"]==r["usage"]["completion_tokens"]
            episode.append(dict(target=res["instance_id"],arm=res["method"],seed=res["seed"],call=len(episode)+1,
                response_id=r["id"],prompt_sha256=h,format_error=fmt,prompt_tokens=r["usage"]["prompt_tokens"],
                completion_tokens=r["usage"]["completion_tokens"],finish_reason=r["finish_reason"]))
        assert len(episode)==traj["info"]["model_stats"]["api_calls"]
        mapped.extend(episode)
    assert len(mapped)==len({r["response_id"] for r in mapped})==75
    fields=list(mapped[0])
    with (args.out/"episode_calls.csv").open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(mapped)
    def group(rows):
        return dict(calls=len(rows),format_errors=sum(r["format_error"] for r in rows),
                    prompt_tokens=sum(r["prompt_tokens"] for r in rows),completion_tokens=sum(r["completion_tokens"] for r in rows))
    unique=sorted({(r["target"],r["arm"]) for r in mapped})
    summary=dict(method="Exact SHA-256 of each native Qwen-rendered task transcript prefix plus the final attempt's time window; accepted actions also verified by response ID and usage.",
       all=group(mapped),by_arm={arm:group([r for r in mapped if r["arm"]==arm]) for arm in sorted({r["arm"] for r in mapped})},
       by_episode=[dict(target=task,arm=arm,seed=0,**group([r for r in mapped if r["target"]==task and r["arm"]==arm])) for task,arm in unique])
    (args.out/"exact_usage.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))


if __name__=="__main__":
    main()
