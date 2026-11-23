"""Select the same new issue IDs for both archived SWE-agent variants, using no labels."""
import gzip
import hashlib
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]
CACHE = Path("D:/CodexResearch/x20-anchor-transfer")
OFFICIAL = Path("D:/CodexResearch/x20-round15-external-scoring")
BENCH = OFFICIAL / "swe-explore.jsonl"
VERIFIED = WORK / "graph_memory_round3/real_swe/official_verified.parquet"
OLD = WORK / "graph_memory_round11/readback/views.gz"
MODELS = ["20240402_sweagent_gpt4", "20240620_sweagent_claude3.5sonnet"]
S3 = "https://swe-bench-submissions.s3.amazonaws.com/"
REPOS = {"astropy/astropy", "matplotlib/matplotlib", "pydata/xarray", "pylint-dev/pylint",
         "pytest-dev/pytest", "scikit-learn/scikit-learn", "sphinx-doc/sphinx", "sympy/sympy"}
EXCLUDE = re.compile(r"\b(?:CVE-\d+|vulnerabilit\w*|exploit\w*|attack\w*|malicious|bypass|injection|denial.of.service|XSS|CSRF)\b", re.I)

def sha(value):
    return hashlib.sha256(value).hexdigest()

def save(name, data):
    b = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    (ROOT/name).write_bytes(gzip.compress(b, mtime=0) if name.endswith(".gz") else b)

def load(path):
    b = path.read_bytes()
    return json.loads(gzip.decompress(b) if path.name.endswith(".gz") else b)

def index(model):
    prefix = "verified/"+model+"/trajs/"
    uri = S3+"?"+urllib.parse.urlencode({"list-type":"2","prefix":prefix})
    b = urllib.request.urlopen(uri,timeout=60).read()
    entries = ET.fromstring(b)
    assert entries.find("{*}IsTruncated").text == "false"
    keys = {r.find("{*}Key").text:r.find("{*}ETag").text.strip('"') for r in entries.findall("{*}Contents")}
    raw_path = CACHE/(model+"-index.xml")
    raw_path.write_bytes(b)
    result = {Path(k).stem:{'key':k,'etag':v} for k,v in keys.items() if k.endswith(".traj")}
    return result, {"size":len(result),"sha256":sha(b),"uri":uri}

def main():
    CACHE.mkdir(parents=True,exist_ok=True)
    indexed = [index(model) for model in MODELS]
    old = set(load(OLD))
    external = {json.loads(l)['instance_id'] for l in BENCH.read_bytes().splitlines() if l.strip()}
    pool = set.intersection(external,*[set(x[0]) for x in indexed]) - old - {"astropy__astropy-12907"}
    vetted = {r["instance_id"]:r for r in pq.read_table(VERIFIED, columns=["instance_id","repo","base_commit","problem_statement"]).to_pylist()
              if r["repo"] in REPOS and not EXCLUDE.search(r["problem_statement"])}
    ids = sorted(pool & set(vetted),key=lambda i:sha(("r16-anchor/"+i).encode()))[:60]
    assert len(old)==199 and 40<=len(ids)<=60 and not old.intersection(ids)
    save("cohort.json",{"tasks":{i:{'repo':vetted[i]['repo'],'base_commit':vetted[i]['base_commit'],
          'trajectories':{m:a[0][i] for m,a in zip(MODELS,indexed)}} for i in ids},"archives":{m:a[1] for m,a in zip(MODELS,indexed)},
          "pool":len(pool & set(vetted)),"r11_n":len(old),"seen_overlap":len(old & set(ids)),"external_ids":len(external),
          "sha_r11":sha(OLD.read_bytes()),"sha_verified":sha(VERIFIED.read_bytes()),"sha_external":sha(BENCH.read_bytes())})
    save("cohort.lock.json",{n:sha((ROOT/n).read_bytes()) for n in ("PROTOCOL_RU.md","cohort.py","cohort.json")})
    print(len(ids),len(pool & set(vetted)),sorted({vetted[i]['repo'] for i in ids}))

if __name__=="__main__":
    main()
