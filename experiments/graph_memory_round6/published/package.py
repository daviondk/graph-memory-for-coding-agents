from pathlib import Path
from hashlib import sha256
from zipfile import ZipFile,ZIP_DEFLATED
import json
import subprocess

HERE=Path(__file__).resolve().parent
OUT=HERE/'published_replay.zip'
BASE=HERE.parent


def main():
    source=HERE/'MemTrace'
    commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    assert commit=='5508f8be81025d8aa90726b1e06aef4ea484e577'
    tracked=subprocess.check_output(['git','-C',str(source),'ls-files','-z']).decode().split('\0')
    files={p:p.relative_to(BASE).as_posix() for p in HERE.glob('*') if p.is_file() and p.suffix in ('.py','.md','.log','.gz','.json')
           and p.name!='package_receipt.json'}
    for p in (source/f for f in tracked if f):
        files[p]=p.relative_to(BASE).as_posix()
    for folder in ('measured','multiple_measured','hybrid_measured','external/measured','external/symmetric'):
        for name in ('rendered.jsonl.gz','cost.jsonl'):
            p=HERE/folder/name
            files[p]=p.relative_to(BASE).as_posix()
    for p in (HERE/'external').glob('*.gz'):
        files[p]=p.relative_to(BASE).as_posix()
    for p in [BASE/'version'/'external'/s for s in ('roster_lock.json','sources_lock.json','receipts.json')]+[
        BASE/'version'/'state_lock.json',BASE/'version'/'evaluation_lock.json']:
        files[p]=p.relative_to(BASE).as_posix()
    for name in ('roster_lock.json','sources_lock.json','receipts.json','decisions_lock.json'):
        p=BASE.parent/'graph_memory_round5'/'action_transfer'/name
        files[p]='published/provenance/kimi/'+name
    inventory={n:sha256(p.read_bytes()).hexdigest() for p,n in files.items()}
    with ZipFile(OUT,'w',compression=ZIP_DEFLATED,compresslevel=6) as z:
        for p,n in sorted(files.items(),key=lambda r:r[1]):
            z.write(p,n)
        z.writestr('SHA256.json',json.dumps(inventory,sort_keys=True,indent=2))
    with ZipFile(OUT) as z:
        assert z.testzip() is None
        assert all(sha256(z.read(n)).hexdigest()==dg for n,dg in inventory.items())
        locks=[n for n in inventory if n.startswith('published/') and n.count('/')==1 and n.split('/')[-1] in
               ('design_freeze.json','method_freeze.json','prediction_freeze.json','multi_freeze.json',
                'multi_predictions.json','hybrid_freeze.json','hybrid_predictions.json','lru_design.json','external_design.json',
                'external_methods.json','external_predictions.json','symmetry_design.json','symmetry_method.json','symmetry_predictions.json')]
        assert len(locks)==14
        import posixpath
        for f in locks:
            for name,digest in json.loads(z.read(f))['files'].items():
                assert inventory[posixpath.normpath('published/'+name)]==digest
    receipt={'sha256':sha256(OUT.read_bytes()).hexdigest(),'bytes':OUT.stat().st_size,
             'members':len(inventory)+1,'source_commit':commit,'verified_freezes':len(locks)}
    (HERE/'package_receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
    print(receipt)


if __name__=='__main__':
    main()
