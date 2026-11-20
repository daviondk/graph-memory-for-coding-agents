---
license: cc-by-4.0
language:
- en
tags:
- swe-bench
- code-retrieval
- information-retrieval
- software-engineering
- benchmark
- reproducibility
task_categories:
- text-retrieval
size_categories:
- n<1K
configs:
- config_name: default
  data_files:
  - split: test
    path: results/instances.jsonl
pretty_name: "SWE-bench Verified file localisation, with a floor"
---

![Localisation on SWE-bench Verified: 45.8 times chance at ranking the right file first, 229 of 500 measured against a permuted-query floor of 5 of 500](https://huggingface.co/datasets/RiverRider/swebench-localisation/resolve/main/figs/og.png)

# Finding the file: localisation on SWE-bench Verified

Given a GitHub issue, which file do you have to change? This is the retrieval step every coding
agent performs before it writes a patch, and none of the leaderboards score it separately. SWE-bench's five
leaderboards all score **% Resolved**, which folds localisation and patch-writing into one
number.

This bundle is that step measured on its own, on all 500 instances of SWE-bench Verified, with a
floor. The write-up is
[Finding the File](https://huggingface.co/blog/RiverRider/finding-the-file-localisation-on-swe-bench-verifie).

```
recall@1   229/500  (0.458)
floor@1      5/500  (0.010)   the same query permuted onto another instance
grep        58/500  (0.116)   text search for the issue's own terms, repaired 2026-09-21
ceiling    477/500  (0.954)   gold file anywhere in the top 50, by passage rank
```

The margin over grep is **+0.342 absolute**. An earlier version of this card read 35/500 and quoted the
margin as a multiple; that grep arm had no idf and no length normalisation and was never given the
per-instance exclusions the retriever gets. Repaired and re-run over the same 500 instances at the same
`base_commit`s it reads 58/500, paired 55 to 34 discordant at exact two-sided p = 0.03342. The
retriever's own three figures never touched that code and are unchanged.

**The floor is the point.** It is what turns 0.458 from a number into a claim. Five instances in
500 return the gold file first for an issue that has nothing to do with them, so 0.458 is
measured against 0.010 and not against zero. Almost no retrieval evaluation reports one, and it
costs a single extra query per instance.

## Verify it without trusting us

Every instance ships its **top-50 candidate list**: the ranked source paths, their scores and the
matched line. So the headline is arithmetic you can redo, not a claim you have to accept.

```
python3 tools/verify_bundle.py .
```

Stdlib only. No model download, no network, no code of ours beyond the 60-line checker. It
recomputes every number in the table above from `results/instances.jsonl`, re-derives each gold
rank from the shipped candidate list, and asserts the 500 ids are distinct. On this bundle it
reports **500 checked, 0 disagree**. If it disagrees with this README, this README is wrong.

![Localisation against a permuted-query floor on SWE-bench Verified](https://huggingface.co/datasets/RiverRider/swebench-localisation/resolve/main/figs/fig1_floor.png)

*The same 500 questions, asked against the same stores, with the issue text shuffled between
instances. Ranking the right file first happens 45.8 times more often than chance. At k = 50 the
same system is 3.9 times chance, which is why a `recall@k` without a floor is not a result.*

## What is here

| path | contents |
|---|---|
| `results/instances.jsonl` | 500 records: gold files, rank, top-50 candidates, floor rank and which instance the floor query came from, text-search result (the withdrawn arm's as `grep_file_withdrawn`), searchable source count, store settings, machine |
| `results/grep_repaired.jsonl` | the repaired text-search arm, 500 records: `okEx` is the arm stated above (58), `ok` the same scorer without the retriever's exclusions (50), `okLegacy` the withdrawn scorer on the same files (37) |
| `questions.json` | the 500-item question set: issue text, gold file(s), per-instance exclusions, `base_commit` |
| `summary.json` | pooled and per-repository aggregates |
| `tools/` | the harness that produced it and the checker that verifies it |

## Per repository, because the pooled number hides the spread

![recall@1 by repository against its own floor](https://huggingface.co/datasets/RiverRider/swebench-localisation/resolve/main/figs/fig2_repos.png)

*django is 46.2% of the benchmark and the hardest repository in it at 0.429. Reporting one pooled
number lets a system trade django for the small arms and show a gain it did not earn.*

| repository | n | recall@1 | floor@1 | grep | ceiling |
|---|---:|---:|---:|---:|---:|
| django/django | 231 | 0.429 | 0.004 | 0.134 | 0.957 |
| sympy/sympy | 75 | 0.480 | 0.013 | 0.067 | 0.933 |
| sphinx-doc/sphinx | 44 | 0.523 | 0.000 | 0.045 | 0.932 |
| matplotlib/matplotlib | 34 | 0.265 | 0.000 | 0.000 | 0.941 |
| scikit-learn/scikit-learn | 32 | 0.688 | 0.000 | 0.219 | 1.000 |
| astropy/astropy | 22 | 0.455 | 0.000 | 0.273 | 0.909 |
| pydata/xarray | 22 | 0.545 | 0.000 | 0.045 | 1.000 |
| pytest-dev/pytest | 19 | 0.526 | 0.158 | 0.158 | 0.947 |
| pylint-dev/pylint | 10 | 0.500 | 0.000 | 0.300 | 1.000 |
| psf/requests | 8 | 0.375 | 0.000 | 0.000 | 1.000 |
| mwaskom/seaborn | 2 | 0.000 | 0.000 | 0.000 | 1.000 |
| pallets/flask | 1 | 0.000 | 0.000 | 0.000 | 1.000 |

*The grep column is the repaired arm, recomputed per repository on 2026-09-21. Every cell in it moved and
django's more than trebled. The `recall@1`, floor and ceiling columns never called that code.*

**django is 231 of 500, 46.2% of the set.** The pooled figure therefore sits close to django's own
0.429 by construction, and comparing it against a system measured on a different mixture compares
mixtures as much as methods. Read the rows, not the total.

**The floor is not uniform.** 5 in 500 pooled, but 3 of those 5 are pytest's, 3 in 19. A pooled
0.010 understates how easy pytest is.

**seaborn (n=2) and flask (n=1) support no rate.** They are listed at 0.000 rather than dropped,
because dropping them would silently change the denominator.

## The method

`BAAI/bge-small-en-v1.5`, 384 dimensions, off the shelf. Source files are cut into passages of
about 420 characters and embedded; rows are stored quantised to 4 bits after the pool mean is
subtracted; ranking is by the centred dot product, then a rerank on shared word stems and
figures; K = 50. One store is built per instance at that instance's `base_commit`, and test and
documentation trees are excluded per instance, with the exclusion list recorded in every record.

Nothing here requires our engine to check: the encoder is public and the pipeline is four steps.
A float32 reimplementation of those steps, with a global mean, line-boundary chunking and a guessed
rerank weight, reads `recall@1` 0.3760 against 0.4501 on 391 of these instances (97 discordant
pairs, 63 to 34, exact McNemar p = 0.00423), so a rebuild should expect the shape of the result
rather than the number. The engine's own path, replayed with its encoder in float32 under PyTorch
on a CUDA GPU and every later step as published, reads 230 against the published 229, with the
rank-1 outcome equal on 495 of 500 instances.

## What this covers, and where it stops

**It covers the whole benchmark.** All 500 instances, twelve repositories, a floor on every one,
and every per-instance candidate list published. Within that population the figures are exact and
you can recompute them in one command. The boundaries below are where the population ends, not
hedges on what is inside it.

**It is the sub-task, measured because it was not being measured.** SWE-bench scores % Resolved,
which folds localisation and patch-writing together. Agentless and the agents on those
leaderboards all perform this step; none reports it separately, so there is no published
localisation number on this split to sit beside. Producing that comparison needs someone else's
system run on these instances with a floor computed the same way.

**Per-instance ranks are not portable between the engine's two memory paths.** A host takes one
or the other depending on whether the page's WebGPU encoder loads: on the page's path, behind every
figure above, rows are stored at 4 bits around the mean and ranked by the centred dot; on the
worker's path a wasm reader indexes the same passages at 8 bits in its own index. On 49 paired
instances over three repositories, run on an M2 Ultra that took the page's path and an EPYC box
that took the worker's, with the same sources and passages and the text-search column agreeing on
all 49, **30 of 49 ranks differ and 14 cross rank 1**. The aggregate is far steadier, moving by
two instances in 49, because the crossings are near-symmetric. An earlier version of this card
called this a difference between CPU architectures; the per-instance files show the box's page
store held no rows, so the two machines ran different paths, and the 30 cannot be attributed to
the CPU.

That is not run-to-run noise, and the control is in this bundle. **95 instances were re-run on the
same machine and path from a separate checkout, at a different time, under three-way contention: 0
of 95 ranks differ**, with the text-search column and every floor rank also identical. Both of
these controls ran against the pre-repair text-search arm. That arm was deterministic, which is the
only property a control needs, so the repair does not reach either result.

Every number here is from one machine, an M2 Ultra running Darwin on `arm64`, which is the
condition under which it means anything. **340 of the 500 records carry a `machine` field and
every one reads `arm64`. The other 160 predate the field** and rest on our word. They are the
astropy, flask, matplotlib, pylint, seaborn, sympy and xarray arms. `base_commit` and the
exclusion count are present on all 500.

**Recall is higher where the issue uses the file's own vocabulary, and not where it quotes the
path.** 0.495 against 0.411 when the gold file's stem appears as a word (p = 0.0705, not
significant); it **inverts** to 0.438 against 0.465 when the filename with its extension actually
appears. Being handed the path buys nothing. The effect is topical overlap, and it strengthens to
0.516 against 0.366 once ordinary stems like `base` and `query` are removed.

The useful half of that: text search falls from **0.174** on the named half to **0.041** on issues
that do not use the file's name, while this falls only from **0.495** to **0.411**. The margin over
text search is +0.370 on the harder half against +0.320 on the named half. An earlier version of
this card gave those as multiples of the withdrawn arm, 10.0x and 5.3x; on the repaired arm the
harder half's multiple rests on 9 hits in 219, so the margin is the figure to carry.

**One lever was tried and refuted.** Promoting candidates whose filename stem appears in the
issue costs seven to fourteen rank-1 hits in 500 and moves between two and four instances down
for every one it lifts (Wilcoxon p = 0.0001 on the ≤2-match variant). It is recorded because the
next person will have the same idea.

## Corrections

This measurement produced thirteen corrections to its own published claims, all dated and kept
rather than overwritten. Among them: a recall figure that belonged to its store rather than the
method; a prefix exclusion that could not reach nested test trees; a `k/n` constant withdrawn
after its denominator was found to count query-time-excluded files; a median rank pinned at `1/n`
wherever recall exceeds 0.5; the cross-deployment instability above; a pooled `n` that counted
rows rather than distinct instances, inflating an earlier figure by six duplicate rank-1 rows;
and the naming caveat above, which was measured on 103 instances and changed in both size and
cause at 500.

Five arrived after this dataset was published. The lever table was still quoted against the
withdrawn `recall@1` of 125/269 until it was re-run on all 500 candidate lists, and the guard
written for that re-run showed `rank` to be a passage position rather than a position among
distinct files. The cross-deployment result was one step from being generalised to leaderboards
that rank float32 models, where a float32 test across `arm64` and `x86-64` moves 1 query in 300.
Two figures on this card pointed at filenames that were not on disk. The text-search arm was
repaired, above. And the cross-deployment result was first read as two CPU architectures when
the two machines had run the engine's two memory paths. `tools/lever_eval_500.py` ships here so
the first of those is checkable rather than asserted.

The withdrawn figure was `recall@1` 125/269. It is superseded by this table rather than adjusted,
because it cannot be reconstructed from the artifacts now on disk.

## Licence and citation

Artifacts and harness under CC BY 4.0. The question set derives from
[SWE-bench Verified](https://www.swebench.com/), whose licence and citation apply to the
underlying instances.

Sunstone North Labs. Contact: burton@sunstonenorth.com
