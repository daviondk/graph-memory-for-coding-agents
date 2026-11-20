# Reproduction

The basic verifier uses the Python standard library. It checks mechanical EM/F1, logical token counts, cue coverage, paired point estimates and wins/losses, SHA-256 links to the trial archive and all eighty blind-judge handoff records.

```text
python verify_highlight.py
```

With NumPy and the parent concord/grade.py, this command also recomputes all 10,000 question-level paired bootstrap intervals and the exact two-sided sign tests from the compact projections, without model, server or internet.

```text
python grade_highlight.py --offline
```

Full-source reconstruction uses parent concord/experiment.py, upstream at commit 4116936349995f0f30597931c0dbbebcbf7e58ac, parent baseline trials and HTTP receipts, its pinned model service and Python dependencies. Set PYTHONUTF8=1 on Windows because the upstream runtime writes source files with the process default encoding. Execute run.py cpu, run.py run, then grade_highlight.py. Completed worker archives are reused by run.py. To reconstruct independently from scratch, copy the project into a new directory keeping the parent primary experiment and its receipts, and copy just PROTOCOL.md, cue.py and run.py to its empty highlight folder. The original model server is required to generate any missing HTTP receipt. Existing-server latency and batching can differ; hashes refer to this particular measured run. Raw requests and trajectories are local under calls/, trials/ and cpu/. The extension compact verification uses no HF datasets and performs no inference.

The CPU run replayed stock model responses as opaque cached records to drive the official tool loop. The selector received only original/current tool evidence and was unable to inspect answers, question ID, private mutation plans or future requests. Each stock input had to match the original request SHA-256 exactly. The first Windows CPU invocation without UTF-8 mode terminated before a completed case; the retry used the primary experiment's UTF-8 configuration. Both variants use the normal tool-call path, same model settings and cached exact full request matches. The actor's tool returns are input data and never shell commands.
Additional checks are available on the source-side machine. audit_cpu.py verifies actual replacement and both candidate substrings directly in the original HTTP inputs. profile_cpu.py times the stock renderer and the extra online selector in one CPU replay. The saved profile is descriptive and is retained on rerun. official_check.py applies the source repository scorer to all 120 answers after grading. report_ru.py recreates the Russian research note. The derived first-response tool-action table is descriptive. Pairwise quality was preregistered, as were source reads, bytes and whole-trajectory logical costs.
