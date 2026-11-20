"""Once all four experiments are sealed, join original reference lines to the visible parquet rows."""
from pathlib import Path
import gzip,hashlib,json,pickle,time,gc,sys
from datetime import datetime,timezone
from collections import defaultdict
from infer import D,read,sha,save
P=D.parents[1]/"graph_memory_round4/repo"
sys.path.insert(0,str(P))
from data_io import rows
class Safe(pickle.Unpickler):
    def find_class(self,module,name):raise pickle.UnpicklingError("No global objects expected")
def main():
    for k in "ABCF":
        while not (D/(k+"_decisions.json")).exists():time.sleep(3)
    group=defaultdict(dict); audit={}; targets={}
    for k in "ABCF":
        lock=read(k+"_decisions.json")
        assert all(sha((D/(k+"_calls")/name).read_bytes())==h for name,h in lock.items())
        for p in read(k+"_packets.json.gz"):group[p["file"]][p["local_index"]]=p
    for short,long in [("cff","first"),("cfr","random")]:
        src=P/"inputs"/("archive_cross_file_"+long+".gz")
        with src.open("rb") as f:audit[src.name]=hashlib.file_digest(f,"sha256").hexdigest()
        with gzip.open(src,"rb") as f:raw=Safe(f).load()
        for level,records in raw.items():
            fname="java_"+short+"_test_"+level+"_0000.parquet";ids=group[fname]
            for i,r in enumerate(rows(P/"archive_inputs"/fname,["code","file_path","repo_name","gold_snippet_index","context"])):
                if i not in ids:continue
                orig=records[i];p=ids[i]
                assert orig["file_path"]==r["file_path"] and orig["repo_name"]==r["repo_name"]==p["repo"]
                assert orig["code"]==r["code"] and orig["context"]==r["context"]
                g=orig.get("gold_snippet_index",orig.get("golden_snippet_index"))
                assert g==r["gold_snippet_index"]
                targets[p["id"]]=[p["repo"],r["file_path"],orig["next_line"],g,sha(orig["code"])]
        del records,raw,orig,r;gc.collect()
    assert len(targets)==sum(len(v) for v in group.values())
    save("original_targets.json.gz",targets);save("original_targets_receipt.json",dict(utc=datetime.now(timezone.utc).isoformat(),n=len(targets),sources=audit,lock=sha((D/"original_targets.json.gz").read_bytes()),decision_sha={k:sha((D/(k+"_decisions.json")).read_bytes()) for k in "ABCF"}))
    print("Verified target mappings",len(targets),flush=True)
def gold_rows(path):
    while not (D/"original_targets_receipt.json").exists():time.sleep(3)
    targets=read("original_targets.json.gz")
    assert sha((D/"original_targets.json.gz").read_bytes())==read("original_targets_receipt.json")["lock"]
    for i,r in enumerate(rows(path,["gold_snippet_index"])):
        key=path.stem.rsplit("_",1)[0]+"|"+str(i)
        if key in targets:
            rr=targets[key];assert rr[3]==r["gold_snippet_index"];r["next_line"]=rr[2]
        yield r
if __name__=="__main__":main()

