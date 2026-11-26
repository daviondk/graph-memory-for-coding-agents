"""Native POSIX execution on the exact same pinned MemTrace as the file-level study."""
import gzip,hashlib,json,sys,tempfile,time
from pathlib import Path

D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parents[1]/"graph_memory_round40/memtrace_reference"))
from replay import run_case


def sha(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()


def main():
    source=D/"sql-input.json.gz"
    assert sha(source)==json.loads((D/"sql-input-seal.json").read_bytes())["file"]
    rows=json.loads(gzip.decompress(source.read_bytes()));pred={};start=time.perf_counter()
    for k,row in rows.items():
        if not row["blocks"]:
            assert not row["expected"];pred[k]=None;continue
        with tempfile.TemporaryDirectory(prefix="x20-memtrace-ast-") as td:
            p=run_case(Path(td),row["blocks"],tuple(row["changed"]))
        assert p["closed_slots"]==row["expected"]
        pred[k]=p
    result=dict(source=sha(source),runtime_s=time.perf_counter()-start,rows=pred,code=sha(Path(__file__)))
    (D/"native-sql.json").write_text(json.dumps(result,sort_keys=True,separators=(",",":"))+"\n",encoding="utf8")
    print("Verified",len(rows),"cases,",sum(isinstance(p,dict) for p in pred.values()),"nonempty SQL projections.")


if __name__=="__main__":main()

