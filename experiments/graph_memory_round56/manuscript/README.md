# Sharing Retained Git Events in a Graph Memory for Coding Agents

An English working paper for the IEEE ICDE demonstrations track. Open the [four-page PDF](paper.pdf) or the [English interactive replay](replay.html). The two selected NetworkX cases illustrate a gain and a loss. Switch tabs, toggle the held-out judgment, then expand an additional event to inspect its owners and every participating path. Both rankings come from the Git prefix and remain fixed when the annotations are hidden.

### Paper and demonstration sources

- The [editable IEEEtran manuscript](paper.tex) and [bibliography](sources.bib) build with the attached figures. The case replay uses Python's standard library and the [recorded queries](../shared_evidence/long8-queries.json.gz). The [retention diagram](figure.py) is an explicitly constructed example. The [withdrawal figure](withdrawal.png) comes from the [preceding prototype](../../graph_memory_round54/submission/withdrawal.png).
- [Logical policies and gold-free inference](../shared_evidence/PROTOCOL_RU.md), [all panel measurements](../shared_evidence/results.json), [paired query differences](../shared_evidence/paired.json), [size controls](../size_control/results.json), [raw Git verification](../event_intersection/long-git-audit.json).
- [Warm read plans and measurement boundaries](../shared_evidence/PHYSICAL_RU.md), [five paired timing blocks](../shared_evidence/physical-wal-summary.json), [durable storage and restart design](../durable/PROTOCOL_RU.md), [transactional results](../durable/results.json), [restart and rollback checks](../durable/correctness.json).
- [Agent Retrieval Bench protocol](../code2test/PROTOCOL_RU.md), [release-level replication and paired results](../code2test/REPORT_RU.md), [local solver evaluation](../solver/REPORT_RU.md), [long-panel cohort definition](../event_intersection/PROTOCOL_RU.md).
- The older, independent tool-trace demonstration is available in the [R55 archive](../../graph_memory_round55/submission/candidate.zip). Its supplementary video records the earlier scenarios. The new English Git replay is included here.
- The four-page limit includes references. The draft carries an anonymous author placeholder and a Codex disclosure in the acknowledgments. [ICDE demonstrations call](https://icde2027.github.io/cf-demonstrations.html)

### Rebuild and verify

From this directory in a repository checkout, run the following commands.

```sh
python -B replay_english.py --verify
tectonic --only-cached paper.tex
pdfinfo paper.pdf
```

The PDF rebuild uses a local Tectonic bundle with IEEEtran, its BibTeX style and the TeX Gyre fonts. To regenerate the retention drawing, run `python -B figure.py` with ReportLab. To regenerate the HTML and reproduce the screenshot in offline Chromium, run `python -B replay_english.py --capture` with Playwright and its browser installed. The supplied HTML works without Python or a server. A link to a source commit opens GitHub when network access is available.

The stored [verification record](verification.json) reports the text and figure inventory, font embedding and the final file checksums. Sections I–IV distinguish retrospective rank agreement, certification before an archive read, equality after archive recovery, and relevance against the next change. The primary Agent Retrieval Bench contrast has a confidence interval that includes zero.
