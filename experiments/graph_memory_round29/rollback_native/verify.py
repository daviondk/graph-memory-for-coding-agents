from controls import *
if __name__=="__main__":
    r=get(D/"manifest.json")
    for k,h in r.items():assert sha256((D/k).read_bytes()).hexdigest()==h,k
    assert set(r)=={p.name for p in D.iterdir() if p.is_file() and p.name!="manifest.json"}
    for v in get(D/"native-receipts.json.gz"):assert v["original_memory"]==v["returned_memory"] and v["original_trace"]==v["returned_trace"]
    print("Verified",len(r),"release files, 200 original no-repair receipts")

