# Local solver for the VibeMemBench tool loop

The VibeMemBench launcher uses mini-SWE-agent's SWE-bench configuration and its LiteLLM adapter at commit bc85a45654e6348dcc6e4c5a40ad146ed0bb144d. That adapter sends a bash function in the Chat Completions tools field, parses native function calls, and appends observations as tool messages with matching call IDs. We verified both a low-level HTTP exchange and two consecutive calls through the pinned adapter. The resulting bash commands and observations are in smoke.json and smoke-pinned.json. [VibeMemBench launcher](https://github.com/AlibabaResearch/DAMO-ConvAI/blob/7152cf96809b45343ccc1caf7115a7d3fa43f956/VibeMemBench/scripts/run_agent.py) · [Pinned agent configuration](https://github.com/SWE-agent/mini-swe-agent/blob/bc85a45654e6348dcc6e4c5a40ad146ed0bb144d/src/minisweagent/config/benchmarks/swebench.yaml)

The local endpoint serves Qwen/Qwen3-8B revision b968826d9c46dd6066d109eabc6255188de91218 with BF16 weights and non-thinking mode on an RTX 3090. It uses the model's own chat template for function signatures, assistant tool calls and tool observations. The parser converts well-formed Qwen tool-call tags into OpenAI-compatible function objects. Malformed model output reaches the regular mini-SWE-agent format-error path. No shell statements execute on the endpoint. The agent's Docker layer executes commands in the repository container. [Checkpoint](https://huggingface.co/Qwen/Qwen3-8B/tree/b968826d9c46dd6066d109eabc6255188de91218)

The local pilot uses temperature 0.5, top-p 0.95, top-k 20, at most 512 generated tokens per agent step, and a limit of 10 agent steps. The published launcher defaults to temperature 0.5 and 250 steps. Qwen3-8B is a new solver condition. The frozen pilot includes four replicates at each target and condition. The authors' script allocates numbered replicate directories without forwarding the integer to the provider. Our loopback routes ending in /replicate/0/v1 through /replicate/3/v1 initialize a separate GPU generator for each sequence using a hash of a fixed experiment seed, replicate and assistant turn. Arms share that seed schedule. Concurrent requests can microbatch up to four items, subject to an 18,000 padded-token batch budget, with the same per-sequence sampling controls. Different CUDA kernels and padding shapes can still introduce floating-point differences. The native model context ceiling is 40,960 tokens.

The server binds only to IPv4 loopback. The Windows-hosted agent reaches it directly and uses local Docker execution in WSL2. Portable logs record request ID, seed, turn, prompt and output digests, parser result, prompt and generated token counts, latency and batch size. They omit request text, tool arguments and authorization headers. The public agent trajectory separately records its actions. The state records runtime library and GPU versions.

The turn in the seed formula is the number of prior messages with the assistant role passed by mini-SWE-agent. A format-error retry can retain the same seed when the adapter adds only a user-side correction. Its input and conditional token distribution still change.

The host exhausted system commit during the initial four-worker run and rebooted. Four completed episodes were retained. The four interrupted episodes were restarted from clean containers with the same assigned seeds. After reboot the client and endpoint used one worker and one sequence per batch. The checkpoint, tool parser, sampling controls and call/step caps were identical. The original and resumed serving configurations have separate state files. All service requests remain in the append-only log, including work in interrupted attempts. Final episode-window tokens can be separated from the cost of abandoned attempts using the recorded timestamps.

## Reproduction

The server's inference environment uses Python 3.12.13, torch 2.6.0+cu124, transformers 4.51.3, accelerate 1.13.0, tokenizers 0.21.4, huggingface_hub 0.34.4 and safetensors 0.4.5. The separate client environment uses mini-swe-agent 2.2.8 at the pinned commit, LiteLLM 1.109.1 and openai 3.51.0. Make the checkpoint available locally first.

```powershell
python serve.py --model D:\models\qwen3-8b-snapshot --runtime D:\local-solver-run --max-output 512 --port 18991
```

Use model name openai/Qwen/Qwen3-8B, a local placeholder API key and API base http://127.0.0.1:18991/replicate/0/v1 in the client. Increment the replicate index for each paired seed. Enable MSWEA_COST_TRACKING=ignore_errors in mini-SWE-agent because local inference has no billable API rate. Use the following commands to run the independent transport checks in the appropriate client environment.

```powershell
python smoke.py --out smoke.json
python pinned_smoke.py --out smoke-pinned.json
```

manage_service.ps1 supports hidden Windows startup and checked shutdown of just the recorded local inference service. summarize_service.py copies the service receipts and counts usage after the pilot, excluding the five identified integration-test calls.
