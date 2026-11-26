# Second-document retrieval over a Wikipedia title directory

Run `python -B serve.py --port 0` with Python 3.9 or newer and open the loopback URL printed to stdout. The server, routing queries and interface run offline with Python’s standard library and SQLite. Use the case control to compare real hyperlinks, literal title mentions, and the baseline title lookup. Change the question-span rule or suppress an individual passage edge. Inspect candidate order to see the BM25 score, tie order and actual link anchor. The audit button explicitly requests annotated support and the resulting coverage.

The source experiment considered **5,989,847 titles**. The shipped database contains **387 candidate rows across eight illustrative questions** chosen to show gains and losses in both direct-title and hyperlink decisions. For the provided traces the projection retains every eligible direct span, verified hyperlink, eligible literal mention, and the original baseline winner. This preserves the baseline decisions and the ranking after removing one eligible passage edge. The ranker runs a real SQLite query over that trace on every request. Scores and observed evidence were recorded during the full-directory run. The console measures next-document and supporting-title selection.

A direct match requires an exact title span outside the first title’s occurrences in the question, a content word distinct from the first title, and the configured distinct-content-word or document-frequency requirement. Gate `0` admits two or more distinct content words. `59` and `5989` additionally allow a single content word with directory DF up to the indicated value. `off` bypasses question-span routing. If a direct candidate qualifies it takes priority. Otherwise the SQL query selects the best eligible passage edge, falling back to the original baseline winner when that set is empty. The baseline uses the highest-BM25 eligible title occurring verbatim after normalization in the question when such a title exists. Otherwise it searches the full directory. The already opened document is excluded. The within-tier order is BM25 descending, Wikipedia page ID ascending, then source row ID ascending. Suppression removes one passage edge only in the selected evidence mode. If its destination also qualifies through the question or is the frozen baseline winner it can still be selected. The counterfactual changes no scores, observed text or other edges.

## Endpoints

| Path | Purpose |
|---|---|
| `/` | Interactive browser console |
| `/api/cases` | Eight example IDs, first titles and directory size |
| `/api/select` | Live SQLite decision with question, first passage, selected title, route, witness, ranked candidate rows and eligible counts |
| `/api/audit` | Independent support annotations, matched titles, complete coverage, and frozen unsuppressed address for the identical controls |

For the decision and audit pass `q`, `gate=off|0|59|5989`, `mode=href|literal|none` and optionally `suppress=<candidate ID>`. Controls default to the introductory case, threshold 59 and verified hyperlinks. The ranking endpoint never opens the annotation file. Span locations use zero-based, half-open normalized word offsets in JSON and one-based word numbers on screen. The counterfactual audit reports null for the historical choice because that modified branch was not recorded in the experiment.

`python -B test_console.py` starts an isolated server and checks all 96 policy decisions, every possible single-edge omission and malformed inputs. `python -B test_console.py --browser` also exercises the controls, score table and narrow viewport using Playwright and Chromium. These browser dependencies are needed only to rerun the optional UI check. `build.json` identifies the source run and checksums. Rebuilding `directory.sqlite` from the complete corpus requires the research repository, its original corpora, and `build_projection.py`.
