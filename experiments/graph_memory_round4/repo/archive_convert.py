"""Losslessly convert only the two pinned public Java retrieval archive members to Arrow, in order."""
import gzip,hashlib,pickle,gc,json,sys
import pyarrow as pa,pyarrow.parquet as pq
from pathlib import Path
D=Path(__file__).resolve().parent;home=D/"archive_inputs";home.mkdir(exist_ok=True)
class Restricted(pickle.Unpickler):
    def find_class(self,module,name):
        raise pickle.UnpicklingError("objects not needed")
def convert(short,suffix):
    p=D/"inputs"/("archive_cross_file_"+suffix+".gz")
    with gzip.open(p,"rb") as f:raw=Restricted(f).load()
    for level,items in raw.items():
        dest=home/f"java_{short}_test_{level}_0000.parquet";print(dest.name,len(items),sorted(items[0]),flush=True)
        writer=None
        for start in range(0,len(items),96):
            rows=items[start:start+96]
            tab=pa.Table.from_pylist([{"repo_name":x["repo_name"],"file_path":x["file_path"],"code":x["code"],"context":x["context"],"gold_snippet_index":x["gold_snippet_index"] if "gold_snippet_index" in x else x["golden_snippet_index"]} for x in rows])
            if writer is None:writer=pq.ParquetWriter(str(dest),tab.schema,compression="zstd")
            writer.write_table(tab);del rows,tab
        writer.close()
if __name__=="__main__":
    args={"cff":"first","cfr":"random"}
    convert(sys.argv[1],args[sys.argv[1]])
