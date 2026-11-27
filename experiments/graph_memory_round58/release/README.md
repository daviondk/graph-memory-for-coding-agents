# Graph memory demonstration package

[Download the offline package](candidate.zip), extract it, and open `start.html`. The first view lets visitors choose an event snapshot, inspect the post-restart workload and explore 822 recorded editor windows. The other two views show which file retained a historical commit and how a two-file query distinguishes joint events from pair counts. Open the four-page paper or the captioned 1 min 51 s video from the same start page.

The HTML runs offline. For the live SQLite reader, open a terminal inside the extracted `two-files` directory and run `python -B demo.py open-snapshot`. A local URL is printed. For a non-interactive check use `python -B demo.py check-snapshot`. The Python reader uses the standard library.

From this repository directory, `python -B package_demo.py --verify` rebuilds the archive, compares every member, checks local navigation and tests the extracted SQLite reader in an isolated Python process. The working draft has an anonymous author line. [Four-page paper](../manuscript/paper.pdf) · [Measured inputs](../REPORT_RU.md) · [Archive verification](verification.json)
