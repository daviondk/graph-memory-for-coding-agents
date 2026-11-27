# Graph memory for coding agents

[Download the offline package](candidate.zip), extract it into one folder and double-click `start.html`. Choose **Open the graph memory demo** to inspect a restart, compare a reference with a compressed event copy, or change the number of missing file-event IDs. All four browser scenarios run offline. The package includes the four-page English working paper, a 1 min 55 s narrated MP4 and separate English captions. The working author line in the paper is anonymous.

## Visit a real event

From the extracted folder, run the following commands with a standard Python 3 interpreter. The first query replays the 38th post-restart request for the Rich project's `tests/test_console.py`. The cache knows 39 of 40 event IDs. The second command hides one additional cached body to exercise the exact fallback. Both compare their top eight file IDs and scores with a separate complete SQLite computation.

```sh
python -B live_query.py
python -B live_query.py --hide-one
```

The optional two-file browser console uses the SQLite snapshot in `two-files`. Change to that directory and run `python -B demo.py open-snapshot`. The address is printed on the terminal. Stop the local server with Ctrl+C. The start page also links to the earlier checkpoint and NetworkX examples.

## Verify or regenerate the package from the repository

From `experiments/graph_memory_round59/release` run `python -B package_demo.py --verify`. The verifier rebuilds the ZIP, checks every member against its repository source, extracts into a temporary folder, opens the pages with an offline browser and executes both SQLite demonstrations in Python isolated mode without site packages. It also inspects the four-page PDF, the video and captions. The verification requires PyMuPDF, Playwright with Chrome and ffprobe on the verifier's PATH. Visitors need none of these to open the package.

To regenerate the live example from the recorded Git events and original cache implementation run `python -B capture_query.py`. To build a fresh archive run `python -B package_demo.py`. All packaged source files, the ZIP, its per-file checksums and the verification results are retained in the repository.
