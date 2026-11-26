"""Verify this snapshot without a model, network connection or external benchmark data."""
import gzip
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parent


def load(p):
    data=p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix==".gz" else data)


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify():
    manifest=load(root/"manifest.json")["files"]
    for name,sha in manifest.items():
        assert digest(root/name)==sha,name
    for rel in ("author_baseline/blind-manifest.json","author_baseline/strata-manifest.json","tie_audit/manifest.json"):
        m=root/rel
        for name,sha in load(m)["files"].items():
            assert digest(m.parent/name)==sha,name
    base=root/"author_baseline"
    seal=load(base/"blind-seal.json")
    ranks=[json.loads(line) for line in (base/"test500-lexical-residual.jsonl").read_text(encoding="utf8").splitlines()]
    assert digest(base/"test500-lexical-residual.jsonl")==seal["blind"]
    assert len({r["state_id"] for r in ranks})==len(ranks)==500
    assert sum(len(r["ranked_evidence_ids"])==8 for r in ranks)==491
    assert sum(not r["ranked_evidence_ids"] for r in ranks)==9
    assert seal["validation"]["strict"] and seal["validation"]["valid"]
    for folder,summary_path,outcomes_path in ((base,"blind-results.json","blind-outcomes.json"),(root/"tie_audit","results.json","outcomes.json.gz")):
        summary=load(folder/summary_path)
        outcomes=load(folder/outcomes_path)
        assert len(outcomes)==494 and len({r["repo"] for r in outcomes.values()})==171
        for k,tot in summary["successes"].items():
            assert list(map(sum,zip(*(r["metrics"][k] for r in outcomes.values()))))==tot
    strata=load(base/"strata-results.json")
    assert strata["scores"]["overlap"]["states"]==317 and strata["scores"]["no_overlap"]["states"]==177
    assert strata["blind_input_only"]==dict(states=500,flags=953,mismatch=0,states_with_overlap=186)
    print(f"Verified {len(manifest)} files, 3 component manifests, 494 Cal500, 500 Test500, 171 calibration repositories.")


if __name__=="__main__":
    verify()
