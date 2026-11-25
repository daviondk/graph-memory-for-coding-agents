"""Freeze article panel without scoring or model output inspection."""
from pathlib import Path
import gzip
import hashlib
import json
import os

HERE = Path(__file__).resolve().parent
UP = HERE.parent / "revoked_evidence"
BLIND = Path("D:/CodexResearch/x20-r26-squad-qa/blind-input.json.gz")
PRIVATE = Path("D:/CodexResearch/x20-r28-retraction-db")

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)

def save(path, obj):
    raw = (json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw)
    os.replace(tmp, path)

def key(s):
    return hashlib.sha256(s.encode()).digest()

def main():
    capture = read(UP / "capture-plan.json")
    assert sha(BLIND) == capture["input"]
    by = read(BLIND)["qs"]
    titles = {q: by[q][0] for q in capture["questions"]}
    articles = sorted(set(titles.values()), key=lambda t:key("r28-db-timing-v1|" + t))[:16]
    panel = sorted(q for q,t in titles.items() if t in articles)
    assert len(titles)==96 and len(panel)==32
    value = dict(qids=sorted(titles), panel=panel, panel_articles=articles,
                 capture=sha(UP/"capture-plan.json"), design=sha(Path(__file__)),
                 protocol=sha(HERE/"PROTOCOL_RU.md"), upstream_queries=sha(UP/"evaluate_views.py"))
    p=HERE/"plan.json"
    if p.exists():
        assert read(p)==value
    else:
        save(p,value)
if __name__=="__main__":
    main()
