"""Pin official pure Python wheels and materialize exact source files."""
from pathlib import Path
import hashlib, json, os, sys, urllib.request, zipfile
ROOT=Path(__file__).resolve().parent
CACHE=Path(os.environ.get('MEMORY_VALIDITY_CACHE','D:/CodexResearch/x20-validity-releases'))
VERS={'tomli':'1.2.3 2.0.1 2.0.2 2.2.1 2.3.0','pathspec':'0.8.1 0.9.0 0.10.3 0.11.2 0.12.1','humanize':'3.13.1 4.0.0 4.5.0 4.8.0 4.11.0'}
def sha(data):return hashlib.sha256(data).hexdigest()
def canon(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True)
def save(p,obj):p.write_text(json.dumps(obj,indent=1,ensure_ascii=True),encoding='utf8')
def tree(pkg,v):return CACHE/'snapshots'/pkg/v
def main():
    rows=[]
    for pkg,vs in VERS.items():
        for v in vs.split():
            uri=f'https://pypi.org/pypi/{pkg}/{v}/json'
            meta=json.load(urllib.request.urlopen(uri,timeout=30)); candidates=[f for f in meta['urls'] if f['filename'].endswith('none-any.whl')]
            if not candidates:rows.append({'pkg':pkg,'v':v,'skip':'no pure wheel','url':uri}); continue
            wheel=sorted(candidates,key=lambda u:u['filename'])[0]; target=CACHE/'wheels'/wheel['filename'];target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():target.write_bytes(urllib.request.urlopen(wheel['url'],timeout=40).read())
            assert sha(target.read_bytes())==wheel['digests']['sha256']
            obj=tree(pkg,v); obj.mkdir(parents=True,exist_ok=True)
            with zipfile.ZipFile(target) as z:
                for name in z.namelist():
                    if (name.startswith(pkg+'/') and name.endswith('.py')) or name.endswith('.dist-info/METADATA'):
                        path=obj/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(name))
            assert (obj/pkg/'__init__.py').exists()
            rows.append({'pkg':pkg,'v':v,'url':wheel['url'],'sha256':wheel['digests']['sha256'],'upload':wheel['upload_time_iso_8601'],'filename':wheel['filename']})
            save(ROOT/'sources.json',rows)
    print(len(rows),'release entries')
if __name__=='__main__':main()

