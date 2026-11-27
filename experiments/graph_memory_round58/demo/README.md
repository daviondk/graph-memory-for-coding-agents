# Recorded graph-memory experiments

Open [index.html](index.html) directly in a Chromium-based browser. The complete English demonstration and its measurement projection fit in one 57,774-byte file. It works offline.

**SQLite restart.** Choose a history panel, a repository or its panel aggregate, and the checkpoint budget per repository. At 1 KiB or 4 KiB, compare most-recent, largest-body and estimated-demand selection. Cold and full have fixed selection rules. The two stacked bars and numeric table account for snapshot writes, snapshot loading, revision receipts, postings and missing event bodies. The timing table uses the median of three measured repetitions. Select **Show a cost increase** to examine the short-history panel with a padded 4 KiB checkpoint per project. [SQLite experiment](../restart/PROTOCOL_RU.md)

**Agent line cache.** Compare exact bytes served and fully covered editor windows at 4, 16 or 64 KiB under two address formats. The individual-window inspector always uses the original 16 KiB, fixed-width file-grouped pair. It includes all 822 recorded windows with anonymous ordinals, public project and model labels, and counts. Source code, file paths, issue IDs and conversation text are omitted from the embedded trace projection. [Cache experiment](../task_cache/REPORT_RU.md)

**Rebuild.** Run `python -B build.py` from this directory in the research checkout. Run `python -B build.py --verify` to check the generated HTML byte for byte against the current inputs. The builder projects all 216 SQLite runs and cross-checks panel aggregates with the saved benchmark results. Input SHA-256 digests are embedded in the page.

**Test.** With Python Playwright and Microsoft Edge installed, run `python -B verify_ui.py`. For Google Chrome use `--channel chrome`. The check exercises 88 combinations of scope and method, six cache views, individual records, gain navigation, the negative example and a 390-pixel viewport in offline mode. [Verification receipt](ui-check.json)
