"""Build the offline English companion view and optionally capture its opening state.

The primary replay supplies source-ranked files and retention witnesses. The browser
can hide held-out judgments without changing the precomputed ranks.
"""
import argparse
from html import escape
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "demo"))
from show import CASES, build, locate, read


def case_html(case, data):
    sha = data["commit"]
    anchor = data["observed_file"]
    targets = set(data["targets"])
    def table(key, title):
        policy = data["strategies"][key]
        rows = []
        for rank, r in enumerate(policy["top8"], 1):
            target = ' class="target"' if r["path"] in targets else ""
            rows.append(f'<tr{target}><td>{rank}</td><td>{r["votes"]}</td>'
                        f'<td><code>{escape(r["path"].removeprefix("networkx/"))}</code></td></tr>')
        return (f'<section><h3>{title}</h3><p>{policy["decoded_events"]} events · '
                f'{policy["decoded_members"]} file memberships</p><table>'
                '<thead><tr><th>Rank</th><th>Votes</th><th>Candidate in NetworkX</th></tr></thead>'
                '<tbody>'+''.join(rows)+'</tbody></table></section>')
    entries = []
    for e in data["shared_only_events"]:
        members=", ".join(escape(p) for p in e["members"])
        owners=", ".join(escape(p) for p in e["owners"])
        event_sha=e["commit"]
        entries.append(f'<details><summary><code>{event_sha[:12]}</code> · {len(e["members"])} file memberships</summary>'
                       f'<p>Retained by <code>{owners}</code></p><p>Participants <code>{members}</code></p>'
                       f'<p><a href="https://github.com/networkx/networkx/commit/{event_sha}">Source commit</a></p></details>')
    hide = "" if case=="gain" else " hidden"
    return (f'<article data-case="{case}"{hide}><h2>{escape(anchor)}</h2>'
            f'<p class="rev">Ranked before commit <a href="https://github.com/networkx/networkx/commit/{sha}"><code>{sha[:12]}</code></a>'
            f'<span class="judgment"> · Held-out file <code>{escape(", ".join(sorted(targets)))}</code></span></p>'
            f'<div class="tables">{table("own","Own eight events")}{table("shared","All surviving events for this file")}</div>'
            f'<details class="evidence"><summary>Inspect {len(entries)} additional events and their owners</summary>'
            + "".join(entries) + "</details></article>")


def render():
    streams = read("event_intersection/long-events.json.gz")
    logs = read("shared_evidence/long8-queries.json.gz")
    parts = []
    for case, sha in CASES.items():
        repo, row = locate(logs, sha)
        parts.append(case_html(case, build(repo, row, streams[repo])))
    return HEAD + "".join(parts) + TAIL


HEAD = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shared Git events in NetworkX</title><style>
*{box-sizing:border-box}body{max-width:1220px;margin:0 auto;padding:22px 30px 30px;font:15px/1.45 "Segoe UI",sans-serif;color:#19313a;background:#fff}h1{font-size:26px;margin:0 0 10px}nav{display:flex;gap:8px;flex-wrap:wrap;align-items:center}button{font:inherit;border:1px solid #71848a;color:#213c44;background:white;padding:5px 12px;border-radius:4px}button[aria-pressed=true]{color:white;background:#1b514b}label{margin-left:auto}h2{margin:15px 0 2px;font:600 19px/1.3 Consolas,monospace}h3{margin:0;font-size:18px}.rev,section p{margin:4px 0 10px}.rev{overflow-wrap:anywhere}.tables{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}section{border:1px solid #aebbbd;padding:10px 14px;border-radius:4px}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:5px 6px;border-bottom:1px solid #d8dfe0}th{font-size:12px;color:#435a61}code{font-family:Consolas,monospace;overflow-wrap:anywhere}body.gold tr.target{background:#daeee6;color:#054b31;font-weight:700}body:not(.gold) .judgment{display:none}details{padding:.55em;border-top:1px solid #c5d0ce}summary{cursor:pointer;color:#13564c;font-weight:600}a{color:#17534f}.evidence{margin-top:.8em}details p{overflow-wrap:anywhere}button:focus-visible,summary:focus-visible{outline:2px solid #22635b}article[hidden]{display:none}@media(max-width:780px){.tables{grid-template-columns:1fr}label{margin-left:0}body{padding:14px}}
</style><body class="gold"><main><h1>Which earlier changes still support this file?</h1>
<nav aria-label="NetworkX case"><button type="button" data-target="gain" aria-pressed="true">Directed generator</button>
<button type="button" data-target="loss" aria-pressed="false">HITS algorithm</button>
<label><input id="gold" type="checkbox" checked> Highlight the held-out test</label></nav>"""
TAIL = """</main><script>
const buttons=document.querySelectorAll('button[data-target]');
for(const b of buttons) b.addEventListener('click',()=>{for(const v of buttons)v.setAttribute('aria-pressed',String(v===b));for(const a of document.querySelectorAll('article'))a.hidden=a.dataset.case!==b.dataset.target});
document.querySelector('#gold').addEventListener('change',e=>document.body.classList.toggle('gold',e.target.checked));
</script></body></html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    page = HERE / "replay.html"
    payload = render().encode("utf8")
    if args.verify:
        if payload != page.read_bytes():
            raise ValueError("Replay HTML differs from reconstructed NetworkX evidence")
    else:
        page.write_bytes(payload)
    if args.capture:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            ui = browser.new_page(viewport={"width":1200,"height":690}, device_scale_factor=1.5, offline=True)
            ui.goto(page.as_uri())
            assert ui.locator("article:visible tbody tr").count() == 16
            ui.locator("main").screenshot(path=HERE/"networkx-replay.png")
            ui.get_by_role("button",name="HITS algorithm").click()
            assert ui.locator("article:visible tbody tr.target").count() == 1
            ui.locator("#gold").uncheck()
            assert not ui.locator("article:visible .judgment").is_visible()
            ui.locator("article:visible .evidence > summary").click()
            assert ui.locator("article:visible .evidence details").count() == 15
            browser.close()


if __name__ == "__main__":
    main()
