"""Two observed official report schemas, preserving all authenticated raw bytes."""
from common import *
from fetch import validated
import collect_labels as original
from concurrent.futures import ThreadPoolExecutor

def get_one(item):
    key,o=item;m,i,_=key.split('|');b=validated(o);raw=json.loads(b)
    value=raw.get(i,raw)
    if not isinstance(value,dict) or not isinstance(value.get('resolved'),bool):
        raise ValueError(('unknown official schema',m,i,list(raw)))
    name='grades/'+m+'/'+i+'.json.gz'
    d={'model':m,'id':i,'resolved':value['resolved'],'source':o,'sha256':sha(b),'official_report':raw}
    if (ROOT/name).exists():assert read(name)==d
    write(name,d)
    path=ROOT/'grade_bytes'/m/(i+'.json.gz');path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(gzip.compress(b,mtime=0))
    return m+'|'+i,d

def main():
    check('label_schema_lock.json')
    for folder in ('','clean/','shuffle/','strict/'):
        lock=read(folder+'reader_lock.json')
        assert all(sha((ROOT/folder/k).read_bytes())==v for k,v in lock.items())
    original.get_one=get_one;original.main()
    manifest={}
    for key,row in read('labels.json.gz').items():
        path='grade_bytes/'+key.replace('|','/')+'.json.gz';f=ROOT/path;b=gzip.decompress(f.read_bytes())
        manifest[key]={'path':path,'sha256':sha(b),'compressed_sha256':sha(f.read_bytes()),'size':len(b)}
    write('grade_bytes_manifest.json',manifest)
    print('raw report bytes preserved',len(manifest))
if __name__=='__main__':main()
