"""Create local, independently replayable patch files from the blinded handoff."""
from hashlib import sha256
from pathlib import Path
import argparse,json,re

D=Path(__file__).resolve().parent
LOCK='e65b1db110411d36f60e528fe16c0948ae3811f0a9792d5dbd68371fe0009f82'
def main():
    p=argparse.ArgumentParser();p.add_argument('handoff',type=Path);args=p.parse_args()
    hand=args.handoff.resolve();assert sha256(hand.read_bytes()).hexdigest()==LOCK
    rows=json.loads(hand.read_bytes());assert len(rows)==3 and len({x['actor'] for x in rows})==3
    cases={};local={}
    for row in rows:
        actor=row['actor'];assert re.fullmatch(r'actor-[123]',actor)
        ref=Path(row['patch']).resolve();assert ref.is_relative_to(hand.parent) and ref.name=='change.patch'
        data=ref.read_bytes();h=sha256(data).hexdigest();receipt=row['receipt'];assert h==receipt['patch_sha256'] and len(data)==receipt['patch_bytes']
        label=actor.replace('-','_')
        local[label]=data;cases[label]={'path':'patches/'+label+'.diff','sha256':h,'bytes':len(data),'actor_log_sha256':row['log_sha']}
    for key,data in local.items():
        target=D/cases[key]['path'];target.parent.mkdir(exist_ok=True)
        if target.is_file():assert target.read_bytes()==data
        else:target.write_bytes(data)
    out=(json.dumps({'original_sha256':LOCK,'cases':cases},sort_keys=True,indent=2)+'\n').encode()
    dest=D/'locked.json'
    if dest.is_file():assert dest.read_bytes()==out
    else:dest.write_bytes(out)
    print('All three blinded patches match their frozen byte counts and SHA-256.')
if __name__=='__main__':main()
