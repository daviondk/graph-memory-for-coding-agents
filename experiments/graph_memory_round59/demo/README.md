# Reopening graph memory

Open [index.html](index.html) directly in a browser. It contains its stylesheet, code and measured registry and sends no network requests.

1. **Restart ledger.** Start with the three longer histories and choose the demand-weighted subset. Change the horizon to zero, one query or the full continuation and compare the four representations. Each records the same answer. “Show a compressed-copy win” opens a constructed case measured on a physical SQLite connection.
2. **Event inspector.** Select Sphinx in the original sparse workload. Choose the second recorded example, load its immutable events and reveal the top eight files. Commit prefixes, event IDs, memberships and body lengths are reconstructed from the same frozen Git stream. The list highlights previously selected bodies on their first use. Other source evidence can also contribute to the ranking.
3. **Cache budgets.** Select all transfer repositories and the sparse workload. At 4 KiB, joint LRU uses 11,600 bytes. Change to 1 KiB to see why caching postings can cost more than caching bodies alone. The quota applies above the common write cache.
4. **Missing event IDs.** Remove one or two IDs from the constructed example. Switch between the 1/4 KiB limits, densities and repositories in the independently frozen six-project holdout. Aggregate component traffic, ordinary LRU, compressed exact postings and certificate controls come from real experiments.

Run `python -B build.py` to recreate the standalone file. Run `python -B verify_ui.py` with the Playwright Python package and Edge to check its DOM offline. The regression checks cover 102 numerical view settings, real source events, the constructed compression counterexample, the 1 KiB reversal and a 390-pixel mobile viewport. [Browser check](ui-check.json) · [Manuscript](../manuscript/paper.pdf) · [Checkpoint measurements](../references/results.json) · [Holdout](../holdout/results.json)
