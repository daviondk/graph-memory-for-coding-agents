"""Post-primary lexical audit + example of a positive receipt bound to scope and observed source hash."""
import collections,gzip,json,re,hashlib,statistics
from pathlib import Path
D=Path(__file__).resolve().parent
def load(name):return json.loads(gzip.decompress((D/name).read_bytes()))
def size(x):return len(json.dumps(x,sort_keys=True,separators=(",",":")).encode())
def main():
    xs=load("visible-conflicts.gz");allcalls=load("calls.gz");controlled=load("controlled.gz")
    by_summary=collections.Counter("has_failed" if re.search(r"\b\d+\s+failed\b",r["summary"]) else "errors_only" for r in xs)
    singles=[r for r in controlled[:40] if r["shape"]=="direct"]
    edges=[]
    for r in singles:
        if r["xml_status"]!="pass":continue
        edges.append({"source_sha256":r["source_sha"],"selection":r["scope"],"nodes":r["expected_nodes"],"runner":"pytest 8.4.2",
                      "evidence_sha256":hashlib.sha256(r["xml"].encode()).hexdigest(),"status":"pass","xml_bytes":len(r["xml"].encode())})
    checks=[]
    for w in edges:
        for query in singles:
            covered=(w["source_sha256"]==query["source_sha"] and w["selection"]==query["scope"] and sorted(w["nodes"])==sorted(query["expected_nodes"]))
            checks.append({"source":w["selection"],"stored_version":w["source_sha256"],"query_fixture":query["fixture"],"covered":covered,"measured_full_invocation":query["fixture_truth"]})
    data={"natural_failed_counts":by_summary,"n_eligible_rc_zero_by_text_tail":sum(r["rc"]==0 and re.search(r"\|\s*tail\b",r["cmd"]) is not None for r in allcalls),
          "n_visible_fail_with_tail":sum(re.search(r"\|\s*tail\b",r["command"]) is not None for r in xs),
          "edges":edges,"canonical_edge_bytes":[size(w) for w in edges],"pairwise_scopes":checks}
    (D/"diagnostics.json").write_text(json.dumps(data,sort_keys=True,indent=2),encoding="utf8")
    print(json.dumps({k:v for k,v in data.items() if k not in ("edges","pairwise_scopes")}))
if __name__=="__main__":main()
