"""Independently rescore ranks and repeat a small deterministic cross-section from plain text."""
import gzip,hashlib,json,sys,pathlib
from collections import Counter,defaultdict
import pyarrow.parquet as pq
from run import ARMS,os,pickle,np
from features import compute
from io_utils import D,read,save,sha
def records(p):
    with gzip.open(p,'rt',encoding='utf8') as f:return [json.loads(l) for l in f]
def main():
    out={};ti=set();ti_hash=set();tr=set();tr_hash=set();unscorable=[];pairs=0;recalced=0
    with (D/"models.pkl").open("rb") as f:models=pickle.load(f)
    saved=read("results.json")
    for f in sorted((D/"inputs").glob("*.parquet")):
        if "_train_" in f.name:
            rs=records(D/"cache"/(f.stem+".jsonl.gz"));tr.update(r[1].casefold() for r in rs);tr_hash.update(r[2] for r in rs);continue
        preds=records(D/(f.stem+".pred.jsonl.gz"));meta=pq.read_table(f,columns=["repo_name","gold_snippet_index"]).to_pylist()
        hits=defaultdict(lambda:np.zeros(3,dtype=int));rr=defaultdict(float);recheck=set(sorted(range(len(meta)),key=lambda i:hashlib.sha256(f"{i}/{f.name}/audit".encode()).hexdigest())[:24])
        i=-1
        for batch in pq.ParquetFile(f).iter_batches(batch_size=40,columns=["code","context"]):
            for row in batch.to_pylist():
                i+=1;r=preds[i];cs=row["context"];n=len(cs);g=meta[i]["gold_snippet_index"]
                assert i==r[0] and r[1]==meta[i]["repo_name"] and r[2]==hashlib.sha256(row["code"].encode()).hexdigest()
                assert list(map(len,cs))==r[3];ti.add(r[1].casefold());ti_hash.add(r[2])
                if not 0<=g<n:unscorable.append([f.stem,i,n,g])
                for a,ids in r[4].items():
                    assert set(ids)==set(range(n)) and len(ids)==n;pairs+=1
                    hits[a]+=np.array([g in ids[:k] for k in (1,3,5)],dtype=int)
                    if g in ids:rr[a]+=1/(1+ids.index(g))
                if i in recheck:
                    for lines in (3,120):
                        x=compute(row['code'],cs,lines)
                        for arm,m in models.items():
                            if ARMS[arm][0]!=lines:continue
                            rank=sorted(range(n),key=lambda j:0) if n==0 else np.argsort(-m.predict_proba(x[:,ARMS[arm][1]])[:,1],kind="stable").tolist()
                            assert rank==r[4][arm]
                    recalced+=1
        for a,v in hits.items():
            assert v.tolist()==saved[f.stem]["metrics"][a]["hits"]
            assert abs(rr[a]/len(preds)-saved[f.stem]["metrics"][a]["mrr"])<1e-10
    assert not ti&tr
    train_hits=read("fit.json")["train_pos"]
    out.update(verified_orders=pairs,recomputed_full_questions=recalced,verified_split_labels=24000,train_repos=len(tr),test_repos=len(ti),common_repos=len(ti&tr),common_prefix_hashes=len(ti_hash&tr_hash),invalid_test_gold=unscorable,train_targeted=6000,train_valid=train_hits,status="passed")
    save("verification.json",out)
if __name__=="__main__":main()
