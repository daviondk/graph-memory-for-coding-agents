# When the last copy leaves

[Download the offline demo package](candidate.zip), extract the ZIP and open **start.html**. The package contains the interactive eviction lab, an executable SQLite snapshot, the four-page English working paper and a narrated 1 min 50 s walkthrough with captions. The HTML lab, video and paper open directly from disk.

## Execute the real query

The lab illustrates the rule using eight constructed events. The SQLite console replays the 50th recorded dense query after the restart in **jazzband/tablib**, at a prefix of 137 eligible multi-file commits. The anchor is `tests/test_tablib.py`. Its complete history spans 40 events. Both measured policies have 38 relevant bodies resident. When notifications are enabled, the captured exception record contains IDs 94, 116 and 117. ID 116 is also resident, so exactly two bodies still need loading.

With a standard Python 3 interpreter, run this command inside the extracted folder and open the printed localhost address. Each button executes the selected query against the bundled read-only SQLite file. Press Ctrl+C to stop the console.

```console
python -B live_query.py --serve
```

The same two reads are available directly from the terminal.

```console
python -B live_query.py
python -B live_query.py --quiet
```

The maintained record produces one SQL query for the two missing event bodies (8 payload bytes). With notifications disabled throughout the original replay, the independent quiet state needs an extra query for the complete posting (49 bytes). The two modes return the same eight file paths and scores. The example prints their actual SQL statements. A separate full scan independently checks the ranking and incurs no charge in the displayed read ledger. The snapshot contains the durable event prefix and the portion of each recorded cache state needed to replay this read. It illustrates a selected favorable case. The interactive lab includes panel-wide measurements, ties and CPU comparisons.

## Verify the extracted result

In this repository, run `python -B package_demo.py --verify` from this directory. Verification replays the original stream with both production cache policies and checks their stored counters through the selected query. It compares the regenerated database and cache snapshots byte for byte, rebuilds the ZIP with deterministic ordering and timestamps, and extracts it. It executes both SQL modes with isolated Python, clicks both live SQLite browser buttons, checks the three offline lab pages, verifies the paper and UI against their source manifests and fully decodes the video. This developer check uses Python, PyMuPDF, Playwright with Edge, FFprobe and FFmpeg. Visitors only need a browser and a standard Python interpreter for the optional SQLite console.

The nine files in the ZIP are listed with hashes in the verification record. Older demo videos, papers and databases are available separately in the previous release. [Verification record](verification.json) · [Capture from source histories](capture_query.py) · [Packaging and tests](package_demo.py) · [Previous release](../../graph_memory_round59/release/README.md)
