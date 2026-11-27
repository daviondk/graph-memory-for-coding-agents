"""Capture the first genuinely reconstructible one-missing-ID query in the Rich holdout."""
from collections import Counter
from contextlib import closing
from pathlib import Path
import gzip
import json
import shutil
import sys
from tempfile import TemporaryDirectory

HERE=Path(__file__).resolve().parent
R=HERE.parent
sys.path.insert(0,str(R/"reconcile"))
from bench_sketch import BlockStore,Hot,SketchPolicy,XOR,prepare
from summary_cache import POST,EVENT,unpack

def main():
    repo="Textualize/rich"
    stream=json.loads(gzip.decompress((R/"holdout/events.json.gz").read_bytes()))[repo]
    receipts=json.loads(gzip.decompress((R/"holdout/queries.json.gz").read_bytes()))["sketch"]["B/"+repo]
    ops,_=prepare(stream,"B")
    names={}
    for _,paths in stream:
        if len(paths)<=64:
            for path in paths:names.setdefault(path,len(names))
    names={i:p for p,i in names.items()}
    cut=sum(o[0]=="w" for o in ops)//2
    with TemporaryDirectory(dir=HERE) as folder:
        dbpath=Path(folder)/"source.sqlite"
        with closing(BlockStore(dbpath,"filelist",True)) as db:
            reader=None;hot=Hot();idx=0
            for item in ops:
                if reader is None and db.next_id==cut:reader=SketchPolicy(db,hot,XOR,1024)
                if item[0]=="w":
                    _,j,rev,files=item;assert db.append(j,rev,files)
                    if reader is not None:hot.append(j,files);reader.after_write(j,files)
                elif reader is not None:
                    _,f,tie,prior,expected=item
                    old=receipts[idx];idx+=1
                    if old["arms"]["1024/xor"].get("recovered1")==1:
                        packet=reader.cache.items[(POST,f)]
                        assert packet[0]==XOR
                        present=set(hot.incident.get(f,()))
                        payload={j:bytes(db.db.execute("SELECT members FROM event WHERE j=?",(j,)).fetchone()[0]).hex() for j in present}
                        for (kind,j),buf in reader.cache.items.items():
                            if kind==EVENT and f in unpack(buf):
                                present.add(j);payload[j]=buf.hex()
                        entry=dict(project=repo,anchor=f,anchor_path=names[f],query=idx,fence=cut,prefix=db.next_id,
                                   summary_hex=packet.hex(),known=payload,tie=dict(tie),
                                   prior=list(prior),expected=[list(row) for row in expected],
                                   paths={i:names[i] for i in set(tie)|set(prior)|{f}})
                        assert reader.read(f,tie,prior)[0]==expected
                        break
                    assert reader.read(f,tie,prior)[0]==expected
            else:raise ValueError("example missing")
            assert db.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()==(0,0,0)
        shutil.copyfile(dbpath,HERE/"source.sqlite")
    (HERE/"query.json").write_bytes((json.dumps(entry,ensure_ascii=True,sort_keys=True,separators=(",",":"))+"\n").encode())
    print(entry["project"],entry["query"],entry["prefix"],entry["anchor_path"],len(entry["known"]))
if __name__=="__main__":main()
