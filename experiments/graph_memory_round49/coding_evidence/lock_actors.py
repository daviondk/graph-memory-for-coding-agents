"""Seal all three independent submissions before opening any grader-only column."""
import argparse,hashlib,json
from pathlib import Path
from settings import D,P,sha,load,dump

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("expected",nargs=3,help="Three peer-reported hashes in actor-1,2,3 order")
    args=cli.parse_args()
    roots=D/'frozen'; roots.mkdir(exist_ok=True)
    records={}
    for k,h in enumerate(args.expected,1):
        a=f'actor-{k}';folder=P/a;rec=load(folder/'session.json')['frozen'];f=folder/'change.patch'
        assert rec and rec['patch_sha256']==h==sha(f)
        dest=roots/(f'blind{k}.patch')
        if dest.exists():assert dest.read_bytes()==f.read_bytes()
        else:dest.write_bytes(f.read_bytes())
        records[f'blind{k}']={'path':'frozen/'+dest.name,'sha256':h}
    data={'cases':records,'launch_seal':sha(D/'handoff-seal.json')}
    f=D/'locked.json'
    if f.exists():assert load(f)==data
    else:dump(f,data)
    print('All three patches sealed',sha(f))
if __name__=='__main__':main()
