"""Recover SQLite WAL after abrupt writer exit before and after a real commit."""
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from benchmark import HERE,MODES,save
from store import Store,decode

def writer(path,mode,stage):
    store=Store(path,mode)
    if stage=="inside":
        store.db.create_function("cut_power_to_process",0,lambda:os._exit(77))
        store.db.execute("CREATE TEMP TRIGGER stop_writer AFTER INSERT ON main.post "
                         "BEGIN SELECT cut_power_to_process(); END")
    assert store.append(8,"rev-8",(0,1))
    os._exit(78)

def run(folder,mode,stage):
    path=folder/f"{mode}-{stage}.sqlite"
    store=Store(path,mode,True)
    for j in range(8):assert store.append(j,f"rev-{j}",(0,1))
    store.close()
    code=subprocess.run([sys.executable,"-B",__file__,"writer",str(path),mode,stage],
                        cwd=HERE,timeout=20,check=False).returncode
    assert code==(77 if stage=="inside" else 78),code
    store=Store(path,mode)
    size=8 if stage=="inside" else 9
    assert store.next_id==size
    assert store.db.execute("PRAGMA integrity_check").fetchall()==[("ok",)]
    assert [(j,rev,decode(blob)) for j,rev,blob in store.db.execute("SELECT * FROM event ORDER BY j")]==[
        (j,f"rev-{j}",(0,1)) for j in range(size)]
    for f in (0,1):assert store.read(f,{0:0,1:0},[0,1])[0]==[(1-f,size)]
    assert store.append(8,"rev-8",(0,1))==(stage=="inside")
    assert not store.append(8,"rev-8",(0,1))
    assert store.read(0,{0:0,1:0},[0,1])[0]==[(1,9)]
    if mode=="split":
        assert list(store.db.execute("SELECT f,j FROM post ORDER BY f,j"))==[(0,0),(1,0)]
        assert set(store.live)==set(range(1,9)) and store.cold=={0,1}
    store.close()
    return dict(exit_code=code,recovered_events=size,count_after_retry=9,integrity_check="ok")

if __name__=="__main__":
    if sys.argv[1:2]==["writer"]:
        writer(*sys.argv[2:])
    else:
        with TemporaryDirectory(dir=HERE,prefix="crash-") as folder:
            checks={m:{s:run(Path(folder),m,s) for s in ("inside","after")} for m in MODES}
        save(HERE/"crash-results.json",checks)
        print("Passed six independent writer-exit and retry checks.")
