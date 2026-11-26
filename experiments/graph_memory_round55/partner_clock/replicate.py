"""Out-of-panel follow-up frozen after the first external test."""
import gzip
import json
import sys
from clock import HERE, evaluate
from evaluate import contrast, grouped
from prepare import DEFAULT_CACHE, dump, fresh_mirror, read_changes

ROSTER = ("python-attrs/cattrs","jaraco/path","tox-dev/filelock","pallets/werkzeug","aio-libs/yarl",
          "python-rapidjson/python-rapidjson","beartype/beartype","pydantic/pydantic-settings",
          "jcrist/msgspec","hukkin/tomli-w")
MODELS = ("anchor_8","global_128","xor_16","unit","exposure","prior")

def main():
    if sys.argv[1] == "collect":
        inputs, pins = {}, {}
        file = HERE/"replication-pins.json"
        old = json.loads(file.read_bytes()) if file.exists() else {}
        for name in ROSTER:
            repo,head,commits = fresh_mirror(name,DEFAULT_CACHE,old.get(name,[None,None])[1])
            inputs[name] = read_changes(repo,commits)
            pins[name] = [commits[0],head,len(commits)-1]
            print(name,len(commits)-1,flush=True)
        if old:
            assert pins == old
        dump(file,pins)
        dump(HERE/"replication-events.json.gz",inputs)
    elif sys.argv[1] == "grade":
        inputs = json.loads(gzip.decompress((HERE/"replication-events.json.gz").read_bytes()))
        rows = [r for repo,events in inputs.items() for r in evaluate(repo,events,MODELS)]
        by_repo,macro = grouped(rows)
        out = dict(n=len(rows),repos=by_repo,macro=macro,primary=contrast(by_repo,"anchor_8","global_128"),
                   no_queries=sorted(set(inputs)-set(by_repo)))
        dump(HERE/"replication-ranks.json.gz",rows)
        dump(HERE/"replication-results.json",out)
        print(out["n"],out["macro"],out["primary"])
    else:
        raise ValueError("expected collect or grade")

if __name__=="__main__":
    main()
