"""Use exactly the original generation loop. Copy only receipts indexed by a fully matching request checksum."""
from pathlib import Path
import gzip
import json
import shutil
import infer

D=Path(__file__).resolve().parent
J=D.parent/"java_reader"

def main():
    assert infer.sha((D/"infer.py").read_bytes())==infer.sha((J/"infer.py").read_bytes())
    ds=infer.read("long_data_lock.json")
    assert ds["packets"]==infer.sha((D/"long_packets.json.gz").read_bytes())
    original=infer.save
    def intercept(name,value):
        original(name,value)
        if name!="long_input_lock.json":return
        keys={k for a in infer.read("long_assignment.json").values() for k in a.values()}
        dest=D/"long_calls";dest.mkdir(exist_ok=True)
        reused={}
        for key in sorted(keys):
            file=key+".json.gz"
            for segment in ("A","B","Z"):
                prior=J/(segment+"_calls")/file
                if not prior.is_file():continue
                rec=json.loads(gzip.decompress(prior.read_bytes()))
                assert infer.sha(infer.from_str(rec["request"]))==key
                if not (dest/file).is_file():
                    shutil.copyfile(prior,dest/file)
                    reused[key]={"prior":str(prior.relative_to(J)),"sha256":infer.sha(prior.read_bytes())}
                break
        if not (D/"long_reuse.json").exists():
            original("long_reuse.json",{"total_unique":len(keys),"reused":reused,"method":infer.sha(Path(__file__).read_bytes())})
        else:
            assert all((dest/(k+".json.gz")).is_file() for k in infer.read("long_reuse.json")["reused"])
        print("logical",384,"distinct",len(keys),"new",len(keys)-len(infer.read("long_reuse.json")["reused"]),flush=True)
    infer.save=intercept
    infer.main("long")
if __name__=="__main__":main()
