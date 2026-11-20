from pathlib import Path
import concurrent.futures,hashlib,json,requests,shutil,time
ROOT=Path(__file__).resolve().parent
MODEL="BAAI/bge-large-en-v1.5";REV="d4aa6901d3a41ba39fb536a557fa166f842b0e09"
CACHE=ROOT/'weights';NAMES=('config.json','tokenizer_config.json','special_tokens_map.json','tokenizer.json','vocab.txt','model.safetensors')
def main():
    CACHE.mkdir(exist_ok=True)
    tree={z['path']:z for z in requests.get(f'https://huggingface.co/api/models/{MODEL}/tree/{REV}',timeout=45).json()}
    def pull(n):
        x=tree[n];dest=CACHE/n;sha=x.get('lfs',{}).get('oid')
        if dest.is_file() and dest.stat().st_size==x['size']:pass
        else:
            url=f'https://huggingface.co/{MODEL}/resolve/{REV}/{n}?download=true'
            tmp=dest.with_suffix('.partial');err=None
            for k in range(3):
                try:
                    with requests.get(url,stream=True,timeout=(15,90)) as r:
                        r.raise_for_status()
                        with tmp.open('wb') as f:
                            for b in r.iter_content(2**20):f.write(b)
                    assert tmp.stat().st_size==x['size'];tmp.replace(dest);break
                except Exception as e:err=e;time.sleep(1)
            if not dest.exists():raise RuntimeError(n) from err
        with dest.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        if sha:assert sha==actual
        else:assert hashlib.sha1(b'blob '+str(x['size']).encode()+b'\0'+dest.read_bytes()).hexdigest()==x['oid']
        return n,{'sha256':actual,'size':x['size']}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:log=dict(pool.map(pull,NAMES))
    (ROOT/'dense_weights.json').write_text(json.dumps({'model':MODEL,'revision':REV,'files':log},indent=2));print('verified checkpoint')
if __name__=='__main__':main()
