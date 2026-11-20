# Strict shell-attribution sensitivity arm
2026-11-17, entered before official per-issue outcome labels are opened.

Independent audit found that the frozen writer uses a diagnostic summary before checking whether a shell batch contains multiple tests or trailing commands. A summary from one command can consequently be attributed to the last recognized test. Most broad guard-bypass examples are ordinary output redirections and tail pipelines, which can preserve valid test summaries. The broad count is not a count of proven errors.

This added arm filters test evidence conservatively. An eligible event must consist of exactly one recognized test invocation. A simple literal cd directory && prefix and ordinary environment assignments are allowed. Heredocs, pipelines, other shell commands, output/input redirections, shell substitution and command separators in the invocation are excluded. All original file-mutation events remain in the chronology. A fail-to-pass pair can use only eligible events. Writer ranking, notes, size caps, reader code, frozen 96 clean issues, patch bytes and both option orders are otherwise fixed.

Generate two strict-witness calls per clean issue, for 192 assignments. Reuse the identical native reader model and decoding parameters. Seal inputs and reader choices before the outcome collector runs. Primary contrast for this additional sensitivity arm is strict-witness minus frozen witness, averaged over two option orders. Also show strict-witness minus empty and strict-witness minus latest. This arm tests sensitivity to conservative attribution with a reduced evidence coverage. It does not isolate attribution accuracy from that coverage loss. Keep frozen original outcomes and methods intact.

The preparer reads only recorded trajectories, receipts and clean input packets. No official report, correctness labels, choices or outcome score files are opened.

