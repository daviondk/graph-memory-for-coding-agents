"""Public action-to-patch source audit. Never requests report.json or hidden outcomes."""
import collections
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
S3 = "https://swe-bench-submissions.s3.amazonaws.com/"
SALT = "public-link-audit-v1"
EXCLUDE = {"20260217_mini-v2.0.0_claude-4-6-opus",
           "20260219_mini-v2.0.0_gpt-5-2-codex",
           "20260901_mini-v2.4.2_gemini-3-5-flash"}

def sha(b):
    return hashlib.sha256(b).hexdigest()

def save(name, value):
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2).encode()
    if path.suffix == ".gz":
        body = gzip.compress(body, mtime=0)
    path.write_bytes(body)

def read(name):
    path = ROOT / name
    body = path.read_bytes()
    return json.loads(gzip.decompress(body) if path.suffix == ".gz" else body)

def get(url):
    assert "report.json" not in url
    error = None
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"Accept-Encoding":"identity","User-Agent":"memory-research-link-audit/1.0"})
            with urllib.request.urlopen(request, timeout=90) as response:
                body = response.read()
                headers = dict(response.headers)
            return body, headers
        except Exception as exc:
            error = exc
            time.sleep(0.5 * (attempt + 1))
    raise error

def listing(prefix, delimiter=None):
    query = {"list-type":"2","prefix":prefix}
    if delimiter:
        query["delimiter"] = delimiter
    pages, objects, folders = [], [], []
    while True:
        url = S3 + "?" + urllib.parse.urlencode(query)
        body, headers = get(url)
        xml = ET.fromstring(body)
        pages.append({"url":url,"sha256":sha(body),"fetched_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      "response_date":headers.get("Date"),"is_truncated":xml.findtext("{*}IsTruncated")})
        for node in xml.findall("{*}Contents"):
            objects.append({"key":node.findtext("{*}Key"),"bytes":int(node.findtext("{*}Size")),
                            "etag":node.findtext("{*}ETag").strip('"'),"last_modified":node.findtext("{*}LastModified")})
        folders.extend(node.findtext("{*}Prefix") for node in xml.findall("{*}CommonPrefixes"))
        token = xml.findtext("{*}NextContinuationToken")
        if not token:
            break
        query["continuation-token"] = token
    return {"pages":pages,"objects":objects,"folders":folders}

def inventory_folder(folder):
    cache = ROOT / ("inventory/" + folder + ".json.gz")
    listing_data = read("inventory/" + folder + ".json.gz")["listing"] if cache.exists() else listing("bash-only/" + folder + "/")
    patch, trace = {}, {}
    incompatible = collections.Counter()
    for obj in listing_data["objects"]:
        key = obj["key"]
        relative = key.removeprefix("bash-only/" + folder + "/")
        matched_patch = re.fullmatch(r"logs/([^/]+)/patch\.diff", relative)
        matched_trace = re.fullmatch(r"trajs/(?:([^/]+)/)?([^/]+)\.traj\.json", relative)
        if matched_patch:
            patch[matched_patch[1]] = obj
        elif matched_trace and (matched_trace[1] is None or matched_trace[1] == matched_trace[2]):
            assert matched_trace[2] not in trace, (folder, matched_trace[2])
            trace[matched_trace[2]] = obj
        elif key.endswith(".traj.json"):
            incompatible["other_trajectory_path"] += 1
        elif key.endswith("patch.diff"):
            incompatible["other_patch_path"] += 1
    ids = sorted(patch.keys() & trace.keys(),
                 key=lambda issue: sha((SALT + "|" + folder + "|" + issue).encode()))
    out = {"folder":folder,"listing":listing_data,"patch_count":len(patch),"trace_count":len(trace),
           "intersection_count":len(ids),"patch_only_ids":sorted(patch.keys()-trace.keys()),
           "trace_only_ids":sorted(trace.keys()-patch.keys()),"other_layout":dict(incompatible),
           "selection":[{"id":issue,"patch":patch[issue],"trace":trace[issue],
                         "salted_sha":sha((SALT+"|"+folder+"|"+issue).encode())} for issue in ids[:24]]}
    save("inventory/" + folder + ".json.gz",out)
    return {key:value for key,value in out.items() if key != "listing"}

def inventory():
    top = listing("bash-only/", "/")
    save("top_listing.json",top)
    candidates = sorted(prefix.split("/")[1] for prefix in top["folders"]
                        if "mini" in prefix.split("/")[1].lower() and prefix.split("/")[1] not in EXCLUDE)
    out = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        pending = {pool.submit(inventory_folder, folder): folder for folder in candidates}
        for future in as_completed(pending):
            folder = pending[future]
            try:
                item = future.result()
                out.append(item)
                print("LIST",folder,item["intersection_count"],flush=True)
            except Exception as exc:
                out.append({"folder":folder,"listing_error":repr(exc),"selection":[]})
    out.sort(key=lambda item: item["folder"])
    save("selection.json",{"salt":SALT,"excluded_anchors":sorted(EXCLUDE),"folders":out,
                           "fixed_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()})
    save("selection_lock.json",{"selection.json":sha((ROOT/"selection.json").read_bytes()),
                               "audit.py":sha(Path(__file__).read_bytes()),
                               "../EXTERNAL_PROTOCOL.md":sha((ROOT.parent/"EXTERNAL_PROTOCOL.md").read_bytes())})
    print("LOCKED",len(out),"folders",sum(len(item["selection"]) for item in out),"pairs",flush=True)

def validated(obj):
    url = S3 + urllib.parse.quote(obj["key"], safe="/")
    body, headers = get(url)
    etag = headers.get("ETag","").strip('"')
    assert len(body) == obj["bytes"], (url,len(body),obj["bytes"])
    assert etag == obj["etag"], (url,etag,obj["etag"])
    strong_md5 = bool(re.fullmatch("[0-9a-f]{32}",etag))
    if strong_md5:
        assert hashlib.md5(body).hexdigest() == etag, url
    receipt = {"url":url,"bytes":len(body),"etag":etag,"md5_verified":strong_md5,
               "sha256":sha(body),"content_encoding":headers.get("Content-Encoding"),
               "fetched_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "response_date":headers.get("Date")}
    return body, receipt

def signed_changes(body):
    files, current, in_hunk = [], None, False
    for line in body.decode("utf8",errors="replace").splitlines():
        if line.startswith("diff --git "):
            current = [line,[]]
            files.append(current)
            in_hunk = False
        elif line.startswith("@@"):
            in_hunk = True
        elif in_hunk and current is not None and line[:1] in ("-","+"):
            current[1].append(line)
    if not any(change for _, changes in files for change in changes):
        return None
    return files

def patch_id(body):
    if not body.strip():
        return None
    result = subprocess.run(["git","patch-id","--stable"],input=body,capture_output=True)
    words = result.stdout.split()
    if result.returncode == 0 and words and re.fullmatch(b"[0-9a-f]{40}",words[0]):
        return words[0].decode()
    return None

def compare(patch, submitted):
    if submitted is None:
        return {"known_submission":False,"both_nonempty":False,"bytes_equal_nonempty":None,
                "signed_changes_equal":None,"git_patch_id_equal":None}
    both = bool(patch.strip() and submitted.strip())
    signed_patch, signed_submit = signed_changes(patch), signed_changes(submitted)
    pid_patch, pid_submit = patch_id(patch), patch_id(submitted)
    signed_usable = both and signed_patch is not None and signed_submit is not None
    id_usable = both and pid_patch is not None and pid_submit is not None
    return {"known_submission":True,"both_nonempty":both,"patch_nonempty":bool(patch.strip()),
            "submission_nonempty":bool(submitted.strip()),
            "bytes_equal_nonempty":patch==submitted if both else None,
            "signed_changes_equal":signed_patch==signed_submit if signed_usable else None,
            "git_patch_id_equal":pid_patch==pid_submit if id_usable else None,
            "patch_id":pid_patch,"submission_patch_id":pid_submit}

def audit_pair(folder, selection):
    issue = selection["id"]
    relative = "records/" + folder + "/" + issue
    path = ROOT / (relative + ".json")
    if path.exists():
        return json.loads(path.read_text())
    try:
        raw, receipt = validated(selection["trace"])
        payload = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
        trace = json.loads(payload)
        info = trace.get("info")
        info = info if isinstance(info,dict) else {}
        submission = info.get("submission")
        submitted = submission.encode("utf8") if isinstance(submission,str) else None
        config = info.get("config")
        config = config if isinstance(config,dict) else {}
        model = config.get("model")
        model = model if isinstance(model,dict) else {}
        patch, patch_receipt = validated(selection["patch"])
        (ROOT / relative).parent.mkdir(parents=True,exist_ok=True)
        (ROOT / (relative + ".evaluator.patch")).write_bytes(patch)
        if submitted is not None:
            (ROOT / (relative + ".trajectory.patch")).write_bytes(submitted)
        record = {"folder":folder,"id":issue,"salted_sha":selection["salted_sha"],
                  "trace":receipt,"patch":patch_receipt,"submission_sha256":sha(submitted) if submitted is not None else None,
                  "model_name":model.get("model_name"),
                  "model_config_sha256":sha(json.dumps(model,sort_keys=True,ensure_ascii=True).encode()),
                  "model_parameters":{key:model[key] for key in ("model_name","temperature","top_p","top_k","max_tokens","reasoning_effort") if key in model},
                  "schema":{"top_keys":sorted(trace),"info_keys":sorted(info),"config_keys":sorted(config),
                            "model_keys":sorted(model),"submission_type":type(submission).__name__},
                  "comparison":compare(patch,submitted)}
        save(relative + ".json",record)
        return record
    except Exception as exc:
        record = {"folder":folder,"id":issue,"error":repr(exc)}
        save(relative + ".error.json",record)
        return record

def summarize(records):
    groups = collections.defaultdict(list)
    for record in records:
        groups[record["folder"]].append(record)
    folders = {}
    for folder, items in sorted(groups.items()):
        available = [item for item in items if "comparison" in item]
        counters = {"selected":len(items),"retrieval_or_parse_errors":len(items)-len(available),
                    "known_submission":sum(item["comparison"]["known_submission"] for item in available),
                    "both_nonempty":sum(item["comparison"]["both_nonempty"] for item in available),
                    "unknown_submission":sum(not item["comparison"]["known_submission"] for item in available),
                    "models":dict(collections.Counter(str(item["model_name"]) for item in available))}
        for metric in ("bytes_equal_nonempty","signed_changes_equal","git_patch_id_equal"):
            values = [item["comparison"][metric] for item in available]
            counters[metric] = {"equal":values.count(True),"different":values.count(False),"unknown_or_empty":values.count(None)}
        folders[folder] = counters
    return {"folders":folders,"sampled":len(records),"folder_count":len(folders),
            "method":"Fixed per-folder salted SHA sample; direct info.submission UTF-8 vs evaluator patch; no report.json requested"}

def audit():
    lock = read("selection_lock.json")
    for name, digest in lock.items():
        assert sha((ROOT/name).read_bytes()) == digest, name
    selection = read("selection.json")
    jobs = [(folder["folder"],item) for folder in selection["folders"] for item in folder["selection"]]
    records = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        pending = [pool.submit(audit_pair,folder,item) for folder,item in jobs]
        for future in as_completed(pending):
            records.append(future.result())
            if len(records) % 50 == 0:
                print("AUDITED",len(records),"/",len(jobs),flush=True)
    records.sort(key=lambda row:(row["folder"],row["id"]))
    save("records.json.gz",records)
    save("summary.json",summarize(records))
    print("COMPLETE",len(records),flush=True)

if __name__ == "__main__":
    import sys
    {"inventory":inventory,"audit":audit}[sys.argv[1]]()

