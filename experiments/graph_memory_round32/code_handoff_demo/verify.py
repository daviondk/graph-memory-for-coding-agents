"""Compare live queries with published per-event results and certified selections."""
from contextlib import closing
from pathlib import Path
import gzip,json
from serve import ROOT,connect,detail,opened,cases

def main():
    base=ROOT.parent/"handoff_ranges"
    packed=json.loads(gzip.decompress((base/"packets.json.gz").read_bytes()))
    originals={r["group"]:r for r in json.loads(gzip.decompress((base/"outcomes.json.gz").read_bytes())) if r["split"]=="test" and r["scope"]=="main_takeovers"}
    with closing(connect()) as db:
        listed=cases(db);assert {r["g"] for r in listed}==set(originals)
        counts={};presets={};opened_variants=0;native=0
        for r in listed:
            g=r["g"];case=detail(db,g);idx=case["routed"]
            for method in ("forward","boundary"):
                v=opened(db,g,idx,method,512);native+=1
                ref=originals[g]["arms"]["one_wide/"+method]
                assert [int(v["boundary_pair"]),sum(v["hits"][:2])/2,int(v["interior_pair"]),sum(v["hits"][2:])/2,int(idx is not None),v["address_wp"],v["read_wp"],v["address_wp"]+v["read_wp"]]==ref
                expected=packed[case["cp"]].get("material",{}).get(str(idx),{}).get(method,{}).get("keys",[])
                assert expected==[[x["line_no"],x["fp"]] for x in v["rows"]]
                for k in ("boundary_pair","interior_pair"):
                    counts[method+"/"+k]=counts.get(method+"/"+k,0)+v[k]
                if idx is not None and v[("boundary_pair" if method=="boundary" else "interior_pair")]:
                    presets.setdefault(method,g)
                if idx is None:presets.setdefault("unavailable",g)
            for a in case["addresses"]:
                for method in ("forward","boundary"):
                    lo,hi=a["first"],(a["first"]+a["last"])//2
                    v=opened(db,g,a["idx"],method,96,lo,hi);assert 0<=v["read_wp"]<=96 and all(lo<=l["line_no"]<=hi for l in v["rows"])
                    assert sum(l["wp"] for l in v["rows"])==v["read_wp"]
                    assert not opened(db,g,a["idx"],method,0)["rows"];opened_variants+=2
            by={}
            for a in case["addresses"]:by.setdefault(a["path"],set()).add(a["revision"])
            if any(len(v)>1 for v in by.values()):presets.setdefault("versions",g)
        stats={"groups":len(listed),"issues":len({r["issue"] for r in listed}),"native_queries":native,"manual_queries":opened_variants,"pair_counts":counts,"presets":presets}
        (ROOT/"verified.json").write_text(json.dumps(stats,sort_keys=True,indent=2)+"\n",encoding="utf8")
        print(stats)
if __name__=="__main__":main()
