"""Finalize immutable loopback service receipts after the last pilot completion."""
import argparse
import collections
import json
import shutil
import statistics
from pathlib import Path


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("runtime",type=Path)
    cli.add_argument("--out",type=Path,default=Path(__file__).resolve().parent)
    cli.add_argument("--episodes",type=Path,help="final pilot_agent directory with the accepted result.json files")
    cli.add_argument("--expected-episodes",type=int,default=8)
    args=cli.parse_args()
    for name in ("state.json","requests.jsonl"):
        shutil.copyfile(args.runtime/name,args.out/name)
    initial=args.runtime/"first-service"
    if initial.is_dir():
        shutil.copyfile(initial/"state.json",args.out/"state_before_restart.json")
    res_file=args.runtime/"resource-watch.jsonl"
    if res_file.is_file():
        shutil.copyfile(res_file,args.out/"resource-watch.jsonl")
    smoke=json.loads((args.out/"smoke.json").read_text("utf-8"))
    pinned=json.loads((args.out/"smoke-pinned.json").read_text("utf-8"))
    smoke_ids={smoke[k]["id"] for k in ("first","matched_duplicate","follow")}
    smoke_ids.update(pinned[k]["extra"]["response"]["id"] for k in ("first","second"))
    calls=[json.loads(l) for l in (args.out/"requests.jsonl").read_text("utf-8").splitlines()]
    assert len({r["id"] for r in calls})==len(calls) and smoke_ids.issubset({r["id"] for r in calls})
    run=[r for r in calls if r["id"] not in smoke_ids]
    stats=dict(transport_smoke_requests=len(smoke_ids),subsequent_requests=len(run),
               smoke_ids=sorted(smoke_ids))
    if run:
        all_times=sorted(r["wall_s"] for r in run)
        stats.update(prompt_tokens=sum(r["usage"]["prompt_tokens"] for r in run),
                     generated_tokens=sum(r["usage"]["completion_tokens"] for r in run),
                     max_input=max(r["usage"]["prompt_tokens"] for r in run),
                     max_output=max(r["usage"]["completion_tokens"] for r in run),
                     finish_reasons=dict(collections.Counter(r["finish_reason"] for r in run)),
                     observed_call_limits=sorted({r["limit"] for r in run}),
                     observed_temperatures=sorted({r["temperature"] for r in run}),
                     by_replicate=dict(collections.Counter(str(r["replicate"]) for r in run)),
                     tool_counts=dict(collections.Counter(r["tool_count"] for r in run)),
                     batch_sizes_per_request=dict(collections.Counter(r["batch"] for r in run)),
                     caller_latency_s_median=statistics.median(all_times),
                     caller_latency_s_p95=all_times[int(.95*(len(run)-1))],
                     request_span_s=max(r["epoch"] for r in run)-min(r["epoch"]-r["wall_s"] for r in run),
                     peak_cuda_bytes=max(r["cuda_peak_bytes"] for r in run))
    if initial.is_dir():
        before={json.loads(s)["id"] for s in (initial/"requests.jsonl").read_text("utf-8").splitlines()}
        stats["pre_restart_nonsmoke_requests"]=sum(r["id"] in before for r in run)
        stats["post_restart_requests"]=sum(r["id"] not in before for r in run)
    if res_file.is_file():
        resources=[json.loads(s) for s in res_file.read_text("utf-8").splitlines()]
        stats["single_worker_memory"]=dict(samples=len(resources),
                    minimum_system_commit_headroom_bytes=min(r["commit_free_bytes"] for r in resources),
                    minimum_physical_available_bytes=min(r["physical_available_bytes"] for r in resources),
                    peak_solver_private_commit_bytes=max(r["private_commit_bytes"] for r in resources),
                    peak_solver_rss_bytes=max(r["rss_bytes"] for r in resources),
                    peak_gpu_used_MiB=max(r["gpu_used_MiB"] for r in resources))
    if args.episodes:
        intervals=[]
        for p in args.episodes.rglob("result.json"):
            if p.parent.name not in {"seed0","seed1","seed2","seed3"}:
                continue
            rec=json.loads(p.read_text("utf-8"))
            if rec.get("status")=="ok":
                intervals.append((rec["start_ts"],rec["end_ts"]))
        assert len(intervals)==args.expected_episodes
        attributed=[r for r in run if any(a<=r["epoch"]<=b for a,b in intervals)]
        outside=[r for r in run if not any(a<=r["epoch"]<=b for a,b in intervals)]
        stats["successful_episode_windows"]=dict(episodes=len(intervals),requests=len(attributed),
            prompt_tokens=sum(r["usage"]["prompt_tokens"] for r in attributed),
            completion_tokens=sum(r["usage"]["completion_tokens"] for r in attributed))
        stats["outside_final_episode_windows"]=dict(requests=len(outside),
            prompt_tokens=sum(r["usage"]["prompt_tokens"] for r in outside),
            completion_tokens=sum(r["usage"]["completion_tokens"] for r in outside),
            ids=[r["id"] for r in outside])
    (args.out/"service_summary.json").write_text(json.dumps(stats,indent=2),encoding="utf-8")
    print(json.dumps(stats,indent=2))


if __name__=="__main__":
    main()
