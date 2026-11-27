# Graph memory demonstration

Download [candidate.zip](candidate.zip) and extract it. Open `start.html` in a browser. The archive includes the four-page working paper, the narrated walkthrough, two offline interactive views and the small SQLite database illustrating two-anchor retrieval. No installation is needed for the offline views.

For a live SQLite query, open a terminal in the extracted `two-files` folder and run:

```sh
python -B demo.py open-snapshot
```

Open the loopback URL printed by the server. It serves the same ranked files as the offline view. An optional check without starting a server is `python -B demo.py check-snapshot`. Python 3.10 or later with its standard library is sufficient for this packaged reader.

The English working draft carries an anonymous author line. The package is for review and reproduction. [Manuscript source](../manuscript/) · [Study report and raw results](../REPORT_RU.md) · [Build the archive](package.py)
