"""Assess whether simpler controls also meet the same descriptive loss bound."""
import sys
from evaluate import ROOT,load,put,sha,contrast


def run(tag):
    rows=load(ROOT/f"{tag}-outcomes.json.gz");main=load(ROOT/f"{tag}-results.json")
    comps={}
    for a in ["always_dense","random50","margin50"]:
        c=contrast(rows,a,"always_graph")
        rate=main["stats"][a]["rate"]
        comps[a]=dict(rate=rate,fs=c["metric"]["fs"],met=rate<=.60 and c["metric"]["fs"]["ci"][0]>-.01)
    put(ROOT/f"{tag}-controls.json",dict(panels=comps,source=sha(ROOT/f"{tag}-outcomes.json.gz")))
    print(tag,comps)


if __name__=="__main__":run(sys.argv[1])
