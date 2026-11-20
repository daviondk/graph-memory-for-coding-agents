"""Third independent panel with a frozen analytical exposure-based projection."""
import concurrent.futures
import datetime as dt
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
import run
from transfer import MatchedMemory, contrast

REPOS = ["pypa/wheel", "python-trio/trio", "python-hyper/h11", "jazzband/pip-tools", "aio-libs/aiohttp",
         "celery/kombu", "mkdocs/mkdocs", "redis/redis-py", "scrapy/scrapy", "pypa/cachecontrol"]


class ExposureMemory(MatchedMemory):
    def __init__(self):
        super().__init__()
        self.exposure = defaultdict(Counter)

    def observe(self, touched, deleted, index):
        super().observe(touched,deleted,index)
        size = len(touched)
        if 2 <= size <= 20:
            for a in touched:
                for y in touched:
                    if y != a:
                        self.exposure[a][y] += 1 / (size * (size - 1))

    def score(self, anchor, index):
        rankings, experts = super().score(anchor,index)
        if not experts:
            rankings["exposure_matched"] = []
            return rankings, experts
        prior = experts[0]
        prev = self.unit.get(anchor,{})
        variant = self.exposure.get(anchor,{})
        total = sum(variant.get(f,0) for f in prior)
        scale = sum(prev.get(f,0) for f in prior) / total if total else 0
        scores = {f:scale * variant.get(f,0) + 4 * prior[f] for f in prior}
        rankings["exposure_matched"] = sorted(prior,key=lambda f:(-scores[f],-self.frequency[f],f))[:5]
        return rankings, experts


def clone(repo):
    name = repo.replace("/","__")
    url = "https://github.com/"+repo+".git"
    path = run.HERE/"exposure_mirrors"/name
    errors = []
    for _ in range(2):
        proc = subprocess.run(["git","clone","--bare","--single-branch","--depth=240","--no-tags",
                               "--filter=blob:none",url,str(path)],capture_output=True,timeout=180)
        if proc.returncode==0:
            return {"repo":name,"remote":url,"sha":run.git(path,"rev-parse","HEAD").decode().strip(),
                    "n_first_parent":int(run.git(path,"rev-list","--count","--first-parent","HEAD")),"shallow":True}
        errors.append(proc.stderr.decode(errors="replace"))
    return {"repo":name,"errors":errors}


if __name__ == "__main__":
    run.METHODS = run.METHODS + ["mass_matched_raw","exposure_matched"]
    run.Memory = ExposureMemory
    pins_file = run.HERE/"exposure_pins.json"
    if not pins_file.exists():
        (run.HERE/"exposure_mirrors").mkdir(exist_ok=False)
        with concurrent.futures.ThreadPoolExecutor(4) as ex:
            pins = list(ex.map(clone,REPOS))
        pins_file.write_text(json.dumps(pins, indent=2),encoding="utf-8")
    pins = json.loads(pins_file.read_text())
    out = run.HERE/"exposure_run"
    out.mkdir(exist_ok=False)
    log = out/"predictions.jsonl"
    inventory = []
    with log.open("w",encoding="utf-8",newline="\n") as f:
        for p in pins:
            if "sha" in p:
                inventory.append(run.replay(p,run.HERE/"exposure_mirrors"/p["repo"],f))
    study = run.summarize([json.loads(s) for s in log.read_text().splitlines()])
    for block in study.values():
        block["exposure_primary"] = contrast(block,"exposure_matched","unit_smoothed")
    summary = out/"summary.json"
    summary.write_text(json.dumps(study,indent=2),encoding="utf-8")
    sigs = [run.HERE/f for f in ("PROTOCOL.md","EXPOSURE_PROTOCOL.md","run.py","transfer.py","exposure.py")]
    (out/"manifest.json").write_text(json.dumps({"utc":dt.datetime.now(dt.timezone.utc).isoformat(),"manifest":inventory,
         "hashes":{f.name:run.hash_file(f) for f in sigs+[pins_file,log,summary]}},indent=2),encoding="utf-8")
    focus = study["evaluation"]
    print(json.dumps({"n":focus["event_weighted"]["n"],"macro":focus["macro"],"primary":focus["exposure_primary"]},indent=2))
