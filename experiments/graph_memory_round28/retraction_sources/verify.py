from formats import *
if __name__=="__main__":
    r=json.loads((D/"manifest.json").read_bytes())
    for k,v in r.items():
        assert sha(D/k)==v,k
    assert set(r)=={p.name for p in D.iterdir() if p.is_file() and p.name!="manifest.json"}
    m=json.loads((D/"blind-seal.json").read_bytes())
    out=P/"stale-projection";assert sha(out/"questions.json")==m["questions_sha"] and sha(out/"evaluator/labels.json.gz")==m["labels_sha"]
    for k,h in m["history"].items():assert sha(out/"history"/(k+".json.gz"))==h
    print("Verified",len(r),"release files and",len(m["history"]),"private blind histories")

