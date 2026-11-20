"""Verify every read file against the exact base-commit archive and all prediction/score digests."""
from pathlib import Path
import hashlib
import json
import tarfile
import gzip

D=Path(__file__).resolve().parent
OLD=D.parents[1]/"graph_memory_round6/repair/transfer"

def sha(b):
    return hashlib.sha256(b).hexdigest()
def read(p):
    return json.loads(p.read_bytes())
def main():
    lock=read(D/"predictions.lock.json")
    output=[]
    for task,h in lock["predictions"].items():
        predfile=D/"predictions"/(task+".json.gz")
        assert sha(predfile.read_bytes())==h
        pred=json.loads(gzip.decompress(predfile.read_bytes())); file_hashes=pred["file_sha"]
        if task.startswith("sympy"):
            src=OLD/"tasks"/task/"checkout.tar.gz"
            expected=read(src.parent/"ready.json")["sha256"]
        else:
            src=D/"inputs"/task/"base.tar.gz"
            expected=read(src.parent/"source.json")["sha256"]
        assert sha(src.read_bytes())==expected
        seen=set()
        with tarfile.open(src) as tar:
            for member in tar:
                p=member.name.partition("/")[2]
                if member.isfile() and p in file_hashes:
                    s=tar.extractfile(member).read().decode("utf8",errors="replace")
                    if task.startswith("sympy"):s=s.replace("\r\n","\n").replace("\r","\n")
                    assert sha(s.encode())==file_hashes[p],(task,p)
                    seen.add(p)
        assert seen==set(file_hashes)
        output.append({"id":task,"source_sha256":expected,"file_count":len(seen),"prediction_sha256":h})
    result={"n":len(output),"file_reads_matched_to_baseline":sum(x["file_count"] for x in output),"rows":output}
    if (D/"evaluation.lock.json").exists():
        scored=read(D/"evaluation.lock.json")
        assert scored["results"]==sha((D/"results.json").read_bytes()) and scored["rows"]==sha((D/"scores_per_issue.json").read_bytes())
        assert scored["predictions_lock_sha256"]==sha((D/"predictions.lock.json").read_bytes())
        result["score_hashes_checked"]=True
    (D/"source_integrity.json").write_text(json.dumps(result,indent=2),"utf8")
    print(result["n"],result["file_reads_matched_to_baseline"],result.get("score_hashes_checked"))
if __name__=="__main__":main()
