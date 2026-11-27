# When the Last Copy Leaves

[Four-page anonymous working draft](paper.pdf) · [LaTeX source](paper.tex) · [interactive console](../demo/index.html).

The demonstrated mechanism maintains the exact set of graph-event addresses absent from the client’s resident memory. The measurements cover source payload, framed loopback traffic, local processing time, and observed editor-window projections. The paper reports where the method ties other representations. Its scope is exact graph storage and retrieval cost.

Rebuild in this directory with Python, PyMuPDF, ReportLab, Pillow, Playwright with Microsoft Edge, and Tectonic with its IEEEtran bundle. The peer console must already have been built.

```powershell
python -B figures.py
$env:SOURCE_DATE_EPOCH='1'
tectonic --only-cached paper.tex
python -B verify.py
```

[Verification](verification.json) includes page geometry, figure and PDF hashes, embedded fonts, and checks against the experiment registries.
