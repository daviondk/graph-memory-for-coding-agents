import json,pathlib,hashlib,subprocess
p=pathlib.Path("work/sota_round/vibe");r=pathlib.Path("D:/CodexResearch/x20-official-vibe/VibeMemBench")
cohort=json.loads((p/"cohort.json").read_text())
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
manifest={"sources":{
 "paper":"https://arxiv.org/abs/2609.23570",
 "dataset":"https://huggingface.co/datasets/Tongyi-ConvAI/VibeMemBench/tree/"+cohort["dataset_revision"],
 "release":"https://github.com/AlibabaResearch/DAMO-ConvAI/tree/"+cohort["harness_revision"]+"/VibeMemBench",
 "agent":"https://github.com/SWE-agent/mini-swe-agent/tree/"+cohort["agent_revision"]},
 "inputs":{"benchmark/test.parquet":sha(r/"benchmark/test.parquet")},
 "solver_fields":["instance_id","repo","language","problem_statement","image_name","base_commit"],
 "solver_prompt_target_field":"problem_statement",
 "images":[],"memory_inputs":{},"allowlisted_source_digests":{}}
for script in ["scripts/run_agent.py","scripts/run_eval.py","scripts/docker_pool.py","scripts/run_memory.py","scripts/vendor/eval.py","scripts/vendor/log_parsers.py","scripts/vendor/swe_constants.py","mini-swe-agent/src/minisweagent/config/benchmarks/swebench.yaml","mini-swe-agent/src/minisweagent/run/benchmarks/swebench_single.py","mini-swe-agent/src/minisweagent/environments/docker.py"]:
 manifest["allowlisted_source_digests"][script]=sha(r/script)
for t in cohort["targets"]:
 iid=t["instance_id"];img=t["image_name"];repo="/"+t["repo"].split("/")[1];registry=json.loads((p/(iid+".registry.json")).read_text())
 cli=["wsl","-d","CodexX20MSR","--exec","/usr/bin/docker"]
 chk=subprocess.check_output(cli+["run","--rm","--network=none","--entrypoint","/bin/sh",img,"-c",'printf "%s\n" "$PWD"; git rev-parse HEAD; if test -e /testbed; then echo present; else echo absent; fi; git for-each-ref --format="%(refname)" | wc -l; git rev-list --all --count'],text=True).strip().splitlines()
 assert chk[:3]==[repo,t["base_commit"],"absent"]
 desc=json.loads(subprocess.check_output(cli+["image","inspect",img],encoding="utf8"))[0]
 assert any(s.endswith("@"+registry["digest"]) for s in desc["RepoDigests"])
 manifest["images"].append(dict(target=iid,tag=img,registry_digest=registry["digest"],local_config_id=desc["Id"],config_working_dir=desc["Config"]["WorkingDir"],base_commit=chk[1],testbed_before_bridge=chk[2],refs=int(chk[3]),commits_reachable_from_HEAD=int(chk[4]),solver_container_network="none"))
 for method in ["raw_bm25","action_receipt","prior_files"]:
  f=r/"outputs"/"memory"/method/"python"/iid/"memory.txt"
  if f.exists():manifest["memory_inputs"][f"{iid}/{method}"]={"sha256":sha(f),"bytes":f.stat().st_size,"words":len(f.read_text().split())}
(p/"provenance.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf8")
