"""Take a reproducible snapshot of native call and resource receipts without message text."""
import argparse
import json
import shutil
from pathlib import Path
from urllib.request import urlopen


def load_rows(path):
    return [json.loads(x) for x in path.read_bytes().splitlines() if x.strip()]


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--runtime",required=True,type=Path)
    p.add_argument("--out",default=Path(__file__).resolve().parent,type=Path)
    a=p.parse_args()
    a.out.mkdir(exist_ok=True,parents=True)
    for name in ["model_receipt.json","runtime_receipt.json","pinned_smoke.json","seed_smoke.json",
                 "service.json","requests.jsonl","resource-watch.jsonl"]:
        shutil.copyfile(a.runtime/name,a.out/name)
    with urlopen("http://127.0.0.1:18840/props",timeout=10) as f:
        props=json.load(f)
    status={k:props[k] for k in ("total_slots","model_path","build_info","chat_template_caps") if k in props}
    status["context_per_slot"]=props["default_generation_settings"]["n_ctx"]
    data=load_rows(a.out/"requests.jsonl")
    resource=load_rows(a.out/"resource-watch.jsonl")
    # The five probes (pinned adapter first+second, then repeat+repeat+other-seed)
    # preceded all real tasks. Collect stable response IDs from the chronological stream.
    checks=data[:5]
    assert len(checks)==5 and [r["turn"] for r in checks]==[0,1,0,0,0]
    assert [r["replicate"] for r in checks]==[0,0,0,0,1]
    assert all(r["tool_calls"]==1 and r["reason_chars"]==0 for r in checks)
    status["smoke_response_ids"]=[r["id"] for r in checks]
    status["smoke_prompts"]=sum(r["usage"]["prompt_tokens"] for r in checks)
    status["smoke_generations"]=sum(r["usage"]["completion_tokens"] for r in checks)
    status["smoke_decode_tokens_s_range"]=[min(r["timings"]["predicted_per_second"] for r in checks),
                                          max(r["timings"]["predicted_per_second"] for r in checks)]
    status["observed_request_count_at_capture"]=len(data)
    status["http_200_responses_at_capture"]=sum(r["http_status"]==200 for r in data)
    status["resource_samples_at_capture"]=len(resource)
    if resource:
        status["min_gpu_free_mib"]=min(r["gpu_free_MiB"] for r in resource)
        status["max_gpu_used_mib"]=max(r["gpu_used_MiB"] for r in resource)
        status["min_system_commit_free_bytes"]=min(r["commit_free_bytes"] for r in resource)
    (a.out/"observed.json").write_text(json.dumps(status,indent=2),encoding="utf8")
    (a.out/"startup.log").write_text("\n".join((a.runtime/"native.stderr.log").read_text(
        encoding="utf8",errors="replace").splitlines()[:33])+"\n",encoding="utf8")
    print(status)


if __name__=="__main__":
    main()
