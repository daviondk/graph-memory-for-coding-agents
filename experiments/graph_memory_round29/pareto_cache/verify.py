"""Check matched K, invariant, costs and physical layout."""
import argparse
from cache_study import D,init,read,save,sha
FILES=("PROTOCOL_RU.md","cache_study.py","plan.json","build-seal.json","costs.json.gz","latency.json.gz","measurement-seal.json","analyze.py","results.json","REPORT_RU.md","verify.py")
def main():
    p=argparse.ArgumentParser();p.add_argument("--seal",action="store_true");p.add_argument("--private",action="store_true");args=p.parse_args()
    r=read(D/"results.json");b=read(D/"build-seal.json");m=read(D/"measurement-seal.json")
    assert r["contrasts"]["all"]["64"]["rescued"]==161 and r["contrasts"]["all"]["64"]["regressed"]==0
    assert m["strict"]==3456 and m["timings"]==13824 and m["latency"]==sha(D/"latency.json.gz")
    if args.private:
        _,_,_,_,dest=init()
        for arm,v in b["stores"].items():
            assert sha(dest/(arm+".sqlite"))==v["sha"] and v["rows"]==(768 if arm.endswith("8") else 6144)
    out={f:sha(D/f) for f in FILES};path=D/"manifest.json"
    if args.seal and not path.exists():save(path,out)
    assert read(path)==out;print("verified",len(out),sha(path))
if __name__=="__main__":main()
