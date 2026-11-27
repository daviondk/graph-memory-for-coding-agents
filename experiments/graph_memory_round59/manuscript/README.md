# Reopening Graph Memory for Coding Agents

[Four-page working draft](paper.pdf) · [Editable IEEEtran source](paper.tex) · [Offline research console](../demo/index.html)

The draft presents a measured database demonstration. Visitors trace an actual Git query to source events, then compare checkpoint encodings, bounded LRU allocations and an exact single-missing-ID certificate. Table I reports the recovery of one fixed evidence set. Table II and Figure 2 report the six-repository holdout, including the operating points where compressed exact postings won. The appendix to the release contains an independent mathematical and SQLite audit. [Holdout protocol and data](../holdout/PROTOCOL_RU.md) · [Reference audit](../reference_audit/REPORT_RU.md) · [Fast-path cost control](../fast_path/results.json) · [Loopback transport](../transport/results.json)

The four pages include two figures, two tables and six references. The author line is a working placeholder. The holdout measures exact-ranked graph retrieval cost. Its unit is a real repository under deterministic Git query schedules. The coding-agent trace checks have a different population and endpoint.

## Rebuild

From this directory, recreate the plot and console screenshot with `python -B figures.py` (ReportLab, Playwright and Edge). Compile with Tectonic and the IEEEtran bundle. In PowerShell, set `$env:SOURCE_DATE_EPOCH='1'` before running `tectonic --only-cached paper.tex`. On a new installation, first run `tectonic paper.tex` to fetch the required fonts and bundle. Run `python -B verify.py` with PyMuPDF to check pagination, embedded fonts, citations, measured numbers and the release digest. The plot and screenshot generated from the registered outcomes are shipped with the source. [Verification record](verification.json)
