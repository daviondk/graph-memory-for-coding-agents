"""Export minimal source identity / time inputs for source-free offline score verification."""
import json
from lite_inputs import dump
from prepare import ROOT, load_inputs

def run():
    docs, _, _ = load_inputs()
    times = json.loads((ROOT / "github_times.json").read_text(encoding="utf-8"))
    rows = []
    for iid,d in sorted(docs.items()):
        repo = d["repo"]
        number = iid.rsplit("-",1)[-1]
        v = times[repo].get(number, {})
        rows.append(dict(id=iid, repo=repo, pr=number, merged=v.get("merge", ""),
                         provenance=v.get("merge_source", "GHArchive") if v.get("merge") else "unknown"))
    dump("history_times_full.csv", rows)

if __name__ == "__main__":
    run()

