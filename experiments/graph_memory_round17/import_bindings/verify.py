"""Derive every reported count from recorded pytest stages or stock JUnit."""
import collections
import gzip
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from experiment import ROOT,positive,sha,save


def read(name):
    raw=(ROOT/name).read_bytes()
    return json.loads(gzip.decompress(raw) if name.endswith(".gz") else raw)


def xml_rows(text):
    rows=ET.fromstring(text)
    return {r.get("classname")+"::"+r.get("name"):(
        "failed" if r.find("failure") is not None or r.find("error") is not None
        else "skipped" if r.find("skipped") is not None else "passed") for r in rows.iter("testcase")}


def main():
    for seal in ("forecast-seal.json","colorama-lock.json"):
        d=read(seal)
        for n,h in d.get("files",d).items():
            assert sha((ROOT/n).read_bytes())==h
    counts={}
    for tag,filename in [("micropanel","runs.gz"),("colorama","colorama-runs.gz")]:
        sums=collections.defaultdict(collections.Counter)
        for kind,row in read(filename).items():
            field = "native" if tag=="micropanel" else "obs"
            final=row["full"][field]["outcomes"]
            failures={k for k,v in final.items() if not positive(v)}
            assert failures==set(row["failed"])
            methods=row["arms" if tag=="micropanel" else "methods"]
            for arm,names in methods.items():
                assert set(names)<=set(final)
                sums[arm].update(dict(rerun=len(names),caught=len(failures&set(names)),false_reuse=len(failures-set(names))))
            execution=row["selected" if tag=="micropanel" else "actual_selected"]
            assert set(execution.get(field,{}).get("outcomes",{}))==set(methods["bindings"])
        canonical=read("results.json" if tag=="micropanel" else "colorama-results.json")["arms"]
        assert all(canonical[k][m]==v for k,r in sums.items() for m,v in r.items())
        counts[tag]=sums
    for filename in ("cli-checks.gz","other-controls.gz"):
        for version,data in read(filename).items():
            group=data.get("cases",data)
            agg=collections.Counter()
            for kind,row in group.items():
                native=row.get("changed",row.get("selected"))
                oracle=row.get("full",row.get("oracle"))
                stable=row.get("stable",row.get("unchanged"))
                actual=xml_rows(oracle["xml"])
                selected=xml_rows(native["xml"])
                assert not xml_rows(stable["xml"])
                assert len(actual)==26
                failures={k for k,s in actual.items() if s=="failed"}
                assert set(row["missed"])==failures-set(selected)
                agg.update(dict(rerun=len(selected),caught=len(failures&set(selected)),false_reuse=len(failures-set(selected))))
            counts["stock_"+version]=agg
    write=dict(sources=counts,checks="Two forecast seals, actual selected nodeids, recorded phase outcomes, native XML from four stock installations")
    save("verification.json",write)
    print(write)


if __name__=="__main__":
    main()

