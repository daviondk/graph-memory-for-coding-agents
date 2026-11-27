"""Collect six prespecified path histories without retrieving source blobs."""
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

HERE=Path(__file__).resolve().parent
R57=HERE.parents[1]/"graph_memory_round57"
sys.path.insert(0,str(R57/"replication"))
from collect import load,save,remote,snapshot

PROJECTS=("Textualize/rich","numpy/numpydoc","marshmallow-code/marshmallow","jaraco/inflect",
          "python-pendulum/pendulum","PyCQA/isort")


def main():
    ap=ArgumentParser()
    ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    prior=load(R57/"replication/data-seal.json")["earlier_rosters"]
    used={name.lower() for values in prior.values() for name in values}
    for area in ("replication","seed_pair"):
        used.update(k.lower() for k in load(R57/area/"heads.json"))
    assert not used.intersection(k.lower() for k in PROJECTS)
    heads=HERE/"heads.json"
    if not heads.exists():save(heads,{k:remote(k) for k in PROJECTS})
    pins=load(heads)
    assert set(PROJECTS)==set(pins)
    packet=HERE/"events.json.gz"
    receipt=HERE/"raw-objects.json"
    data=load(packet) if packet.exists() else {}
    digests=load(receipt) if receipt.exists() else {}
    for name in PROJECTS:
        if not args.verify and name in data and name in digests:continue
        with TemporaryDirectory(dir=HERE) as temp:
            rows,pin,proof,size=snapshot(name,pins[name],temp)
        obs=dict(pin=pin,proof=proof)
        if args.verify:
            assert data[name]==rows and digests[name]==obs
        else:
            data[name]=rows;digests[name]=obs
            save(packet,data);save(receipt,digests)
        print(name,len(rows),size,"temporary bytes",flush=True)
    assert len(data)==len(digests)==6
    print("Events",sha256(packet.read_bytes()).hexdigest())


if __name__=="__main__":
    main()
