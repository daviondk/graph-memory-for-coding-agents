"""Verify all signed publication variants and replay future agreement from anonymized receipts."""
from shared import D,METHODS,BUDGETS,read,sha
from materialize import boundaries

def main():
    p=read(D/"forecasts.json.gz");a=read(D/"outcomes.json.gz");r=read(D/"results.json");f=read(D/"forecast-seal.json")
    assert set(p)==set(a) and len(p)==2696 and sha(D/"forecasts.json.gz")==f["sha"]
    for fn,hash_ in f["code"].items():assert sha(D/fn)==hash_
    assert sha(D/"outcomes.json.gz")==read(D/"grade-seal.json")["outcomes"] and sha(D/"grade-seal.json")==r["source"]
    for k,v in p.items():
        receipts=set(map(tuple,v["receipt"]))
        for m,arm in v["methods"].items():
            gold=a[k]["write"][m];assert gold.get("all_written",0)==len(arm["proposed"])
            assert gold.get("informative",0)==sum(x[3] for x in arm["proposed"])
            assert gold.get("duplicate_receipt",0)==sum(int(bool(info) and (n,d) in receipts) for n,d,sz,info in arm["proposed"])
            for c in map(str,BUDGETS):
                pack=arm["packs"][c];s=a[k]["metrics"][c][m]
                assert s["wire_bytes"]==sum(x[2]+1 for x in pack)<=int(c)
                assert all((n,d) not in receipts for n,d,sz in pack)
                assert pack==v["methods"]["prior"]["packs"][c]
    for panel,keys in (("held1071",[k for k,v in p.items() if v["held"]]),("all2696",list(p)),("main676",[k for k,v in p.items() if v["group"]=="main"])):
        tab=r["panels"][panel];assert tab["n"]==len(keys)
        for m in METHODS:
            assert tab["write"][m].get("wrong_candidate",0)==sum(a[k]["write"][m].get("wrong_candidate",0) for k in keys)
            for c in map(str,BUDGETS):
                for metric in ("hit","lines","bad_emitted"):
                    assert tab["budgets"][c]["methods"][m].get(metric,0)==sum(a[k]["metrics"][c][m].get(metric,0) for k in keys)
    assert boundaries("x","abc\nend",1,{1:"prexpost"})==({}, {1:"preabc",2:"endpost"})
    assert boundaries("x","abc",1,{1:"xx"})==({}, {})
    i,c=boundaries("x\ny","aa\ninside\nz",4,{4:"beforex"});assert i=={5:"inside"} and c=={4:"beforeaa",5:"inside"}
    if (D/"manifest.json").exists():
        for fn,d in read(D/"manifest.json")["files"].items():assert sha(D/fn)==d,fn
    print("Verified 2696 source observations, 5 methods, 3 equal budgets, actual receipt duplicates and per-episode packet identities.")
if __name__=="__main__":main()

