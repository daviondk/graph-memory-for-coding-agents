"""Compare independently computed call and PU counts in all 4,828 history states."""
from pathlib import Path
import json,gzip,hashlib
D=Path(__file__).resolve().parent;M=D.parent/"materialized_append"
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ours=read(D/"histories.json.gz");source=read(M/"forecast-seal.json");checked=0;counts=0;h={};aligned=read(D/"call-alignment.json")["adjustments"];adjusted=0
    for i in range(8):
        f=M/f"graphs-{i}.json.gz";s=read(f);h[f.name]=sha(f)
        for t,c in s.items():
            mine=ours.pop(t)
            for cut,r in c["states"].items():
                z=mine[cut]
                calls=aligned.get(t+"/"+cut,{}).get("projected_calls",z["call_pairs"])
                for key,field in (("E","exact"),("M","material"),("L","logical")):
                    adjusted+=int(calls[key]!=z["call_pairs"][key])
                    assert calls[key]==r["logical_pairs"][key],(t,cut,key,"call")
                    assert z["pu_pairs"][key]==r[field],(t,cut,key,"PU")
                    counts+=2
                assert z["pu_pairs"]["equal_boundary"]+z["pu_pairs"]["before_boundary"]==r["never_visible"]
                assert z["pu_pairs"]["revoked_materialized"]==r["once_visible"]
                checked+=1;counts+=2
    assert not ours and checked==4828
    result={"counts_with_empty_output_endpoints":adjusted,"endpoint_audit":sha(D/"call-alignment.json"),"states":checked,"equalities":counts,"independent_source":sha(D/"histories.json.gz"),
            "other_seal":sha(M/"forecast-seal.json"),"other_graph_shards":h,"code":sha(Path(__file__))}
    target=D/"cross-check.json"
    if target.exists():assert result==read(target)
    else:target.write_text(json.dumps(result,sort_keys=True,separators=(",",":"))+"\n",encoding="utf8",newline="\n")
    print("Verified",checked,"states,",counts,"pair counts and decompositions")
if __name__=="__main__":main()
