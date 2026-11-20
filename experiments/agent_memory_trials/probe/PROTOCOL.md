# Transferring a diagnostic call between tool releases

Prospective synthetic controlled pilot, written 2026-11-16. The authoritative freeze time in UTC is created by the freeze command after source histories, the concealed target allocation, the scripts and the stage-one requests exist and before any stage-one model answer. The freeze is a local SHA-256 record, without a third-party timestamp. There is no model pilot on these tasks and no optional stopping.

## Question and mechanism

For a tool whose contract may have changed, does retaining one historically discriminating call improve an agent's subsequent predictions, compared with retaining one routine call or designing a fresh probe? Prediction: the saved discriminating input will more often induce an observation that distinguishes the relevant historical alternatives, and increase the chance of four correct application outputs. An agent may invent a better composite probe in every arm. Equal or negative differences will be reported.

## Historical memories, fixed before targets

Six purpose-built contracts cover decimal syntax, date parsing, basename extensions, Unicode length, slug normalization and integer bucketing. Each has a public default and three public optional policies of which at most one can be active. Each family has an earlier and a more recent historical build differing on only one policy. The changed policy index is balanced across families, as is whether the recent historical version implements the default. Two builds each execute the identical synthetic seven-event cassette. Four occurrences repeat a routine input and three cover one edge each. The discriminating selector retains the input and most recent output for the first historical mismatch; the ordinary selector retains the same fields for the modal input. Neither selector receives target inputs, outputs, seed, stability labels or invocation traces. The two selectors are deterministic code, the executor is a live LLM. Both cards are unlabeled in the executor prompt. This design presupposes availability of old version comparisons and deliberately solicits an edge case for each documented option. It studies selection and reuse of a memory, not discovery of failure cases in production. The archive costs 14 historic executions per family; both selectors share it. Fresh probing requires none.

## Targets, batching and concealment

For each family, one target holds the most recent historical policy and one reverts to the previous policy. This produces 12 distinct opaque targets and 36 arm-case combinations. Only the harness knows which target is which. Each pair uses the same archived card but different held-out inputs. A target never introduces a third drift mechanism outside its two historical modes; results only address recurrence of a previously observed distinction. Assignment of target mode to target id is randomized independently of archive generation. Sources are generated before any target. The agent sees the public four-behavior manual without case-specific version labels, deployment frequencies or counterbalancing information. Held-out inputs are concealed during probe design; current outputs remain hidden until scoring. Four fresh inputs per case cover the default and three policy edges in random order. True behavior can be identified if all four outputs are right. A fresh chosen probe can accidentally equal a held-out input; record that event.

Six families are shuffled into two disjoint panels of three. In each panel, one target from each family is in the first matched triple and its counterpart is in the second. Four matched triples are presented under each arm, in randomized request order independent of content. The three different families in a request obviate cross-target direct solving via shared manuals. Across arms each matched triple uses identical cases and order. Separate model requests have clean conversations. Each stage uses 12 model requests; there are 24 in total. Related observations comprise six family pairs, four matched batches, and two disjoint panels that account for both sources of dependence. The 144 graded scalars are repeated measurements. There is one model draw per batch and stage; inference to future models or broad tool distributions is unsupported.

## Procedure and controls

Stage one gives every arm the identical task, per-case public manual and budget of one scalar target call. Discriminating and ordinary arms see one past input/output pair; fresh sees none. The common instruction explicitly invites inventive probes that separate contracts and compound probes whenever valid. The root orchestration starts the same model, reasoning setting and transport wrapper for every arm. A deterministic Python observation server executes the chosen input on the hidden target and passes that exact result to stage two. A malformed proposal yields one error observation and there is no replacement tool call. Stage two receives the same manual and archive as before, the single current observation and four pending application inputs. The decision maker returns four concrete scalar results. It never obtains any other target output. The offline grader executes those pending inputs on the hidden target and uses exact type-sensitive equality. No LLM judge, answer normalization or condition-dependent scoring. An invalid/missing four-output array yields four errors. Transport failures can retry once using the shared runner, while malformed final answers are not retried. Completion of all scheduled cases, including failures, is the stopping rule. Exact prompts, backend events, attempts, statuses, token counters, time, target probe inputs/outputs and individual scores are retained. The runner records technical retries separately.

## Analysis

Primary outcome is all four pending outputs correct for the case. Planned contrasts are the paired difference in perfect-case rates (discriminating minus ordinary and discriminating minus fresh), with counts of per-case wins/ties/losses. Secondary are per-output accuracy, frequency of a target probe that actually distinguishes the two historical modes, exact reuse of the old discriminating input, stable/reverted counts, and resource cost. For each contrast show six family differences, four matched-batch differences, two disjoint panel differences, and leave-one-family/batch-out ranges. These are sensitivity summaries, not confidence intervals. There are only two clusters accounting jointly for family and call grouping; no asymptotic confidence interval or p-value is planned. Report failures and ceilings. No generalized superiority claim from this demonstration.

## Reproduction

Use Python 3.12+ (standard library), same CLI and transport conditions when possible. From the probe folder:

```text
python -X utf8 study.py verify
python -X utf8 ../shared/run_model.py stage1.jsonl runs1 --workers 2
python -X utf8 study.py observe
python -X utf8 ../shared/run_model.py stage2.jsonl runs2 --workers 2
python -X utf8 study.py score
```

For fresh model draws, copy the frozen inputs into a new sibling study directory with a matching ../shared path, omit both run directories and use the same commands. The runner reuses existing records when present. To regenerate the initial sealed files from scratch in a clean directory without freeze.json or run directories, call study.py prepare and then study.py freeze. Raw runs remain stochastic. The scorers and fixture outputs are deterministic and need no external package.

The design and analysis workflow consulted Kassis, Agarwal, He, Patel & Brueckner (2026), *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*, v2, [arXiv:2609.00065](https://doi.org/10.48550/arXiv.2609.00065).
