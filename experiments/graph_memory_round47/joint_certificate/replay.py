"""Run exact joint reoptimization for every preregistered simultaneous change on CPU."""
from pathlib import Path
import argparse,json,os,shutil,subprocess,tempfile
from build import D,load,save,dig
from geometry import probes

def query_lines(q):
    tail=q['tail'];pairs=q['pairs'];source=q['source'];limits=q['limits']
    lines=[f"{len(tail)} {q['cap']} {len(pairs)}"]
    lines.extend(f'{c} {u}' for n,c,u in tail)
    for a,b,label in pairs:
        s=set(source[a]);t=set(source[b])
        primary,diag=probes(limits[a],limits[b]);grid=[(0,0),*primary,*diag]
        lines.extend([str(len(grid)),' '.join(str(int(n in s)+2*int(n in t)) for n,c,u in tail)])
        lines.extend(f'{x} {y}' for x,y in grid)
    return ('\n'.join(lines)+'\n').encode()
def main():
    pars=argparse.ArgumentParser();pars.add_argument('--write',action='store_true');args=pars.parse_args()
    sample=load('sample.json.gz');assert dig(D/'sample.json.gz')==load('sample-seal.json')['sha256']
    cxx=os.environ.get('CXX') or shutil.which('g++')
    records={}
    with tempfile.TemporaryDirectory(dir=D) as tmp:
        exe=Path(tmp)/('joint.exe' if os.name=='nt' else 'joint')
        subprocess.run([cxx,'-std=c++17','-O3',str(D/'oracle.cpp'),'-o',str(exe)],check=True)
        for query,q in sample.items():
            results=subprocess.run([str(exe)],input=query_lines(q),capture_output=True,check=True).stdout.decode('ascii').splitlines()
            start=0;per_pair=[]
            for a,b,label in q['pairs']:
                primary,diag=probes(q['limits'][a],q['limits'][b]);n=1+len(primary)+len(diag)
                masks=results[start:start+n];start+=n
                assert len(masks)==n and masks[0]==q['old'] and all(len(v)==len(q['tail']) for v in masks)
                indices={};table=[]
                for mask in masks:
                    if mask not in indices:indices[mask]=len(table);table.append(mask)
                per_pair.append({'table':table,'idx':[indices[mask] for mask in masks]})
            assert start==len(results);records[query]=per_pair
    if args.write:save('joint-outcomes.json.gz',records)
    assert records==load('joint-outcomes.json.gz')
    print(len(records),sum(len(v) for v in records.values()),'frozen pairs')
if __name__=='__main__':main()
