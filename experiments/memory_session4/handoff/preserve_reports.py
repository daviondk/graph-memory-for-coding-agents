"""Preserve original verified HTTP bytes so official label provenance can be checked offline."""
from concurrent.futures import ThreadPoolExecutor
from common import *
from fetch import validated

def one(item):
    key,row=item
    raw=validated(row['source'])
    assert sha(raw)==row['sha256']
    assert json.loads(raw)==row['official_report']
    name='grade_bytes/'+key.replace('|','/')+'.json.gz'
    f=ROOT/name;f.parent.mkdir(parents=True,exist_ok=True)
    f.write_bytes(gzip.compress(raw,mtime=0))
    return key,{'path':name,'sha256':sha(raw),'compressed_sha256':sha(f.read_bytes()),'size':len(raw)}

def main():
    for folder in ('','clean/','shuffle/','strict/'):
        locked=read(folder+'reader_lock.json')
        assert all(sha((ROOT/folder/k).read_bytes())==v for k,v in locked.items())
    with ThreadPoolExecutor(16) as pool:manifest=dict(pool.map(one,read('labels.json.gz').items()))
    write('grade_bytes_manifest.json',manifest)
    print('preserved raw HTTP bodies for',len(manifest),'source grades')
if __name__=='__main__':main()
