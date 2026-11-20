from pathlib import Path
import hashlib,json,urllib.request,zipfile
D=Path(__file__).resolve().parent
def main():
    packages={}
    for v in ['3.4.2','3.5']:
        meta=json.load(urllib.request.urlopen('https://pypi.org/pypi/networkx/'+v+'/json',timeout=30))
        wh=next(v0 for v0 in meta['urls'] if v0['filename'].endswith('.whl'))
        buf=urllib.request.urlopen(wh['url'],timeout=60).read()
        assert hashlib.sha256(buf).hexdigest()==wh['digests']['sha256']
        path=D/'vendor'/wh['filename'];path.parent.mkdir(exist_ok=True);path.write_bytes(buf)
        target=D/'vendor'/v
        with zipfile.ZipFile(path) as z:
            for f in z.namelist():
                assert not Path(f).is_absolute() and '..' not in Path(f).parts
            z.extractall(target)
        packages[v]=dict(wheel=wh['filename'],sha256=wh['digests']['sha256'],url=wh['url'],python=meta['info']['requires_python'])
    (D/'release_lock.json').write_text(json.dumps(packages,indent=2),encoding='utf8')
if __name__=='__main__':main()