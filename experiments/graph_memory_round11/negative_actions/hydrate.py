"""Hydrate missing Git blob objects via public codeload; check path+blob IDs against fetched commits."""
import hashlib, io, os, tarfile, urllib.request, zlib
from concurrent.futures import ThreadPoolExecutor
from harvest import D, get, save, sha
from git_pairs import local,git
def fetch(item):
    repo,rev=item
    root=local(repo)
    tree={}
    for seg in git(root,"ls-tree","-r","-z",rev).stdout.split(b"\0"):
        if not seg:continue
        attrs,p=seg.split(b"\t",1);mode,kind,oid=attrs.decode().split()
        if kind=="blob":tree[p.decode()]=(oid,mode)
    url=f"https://codeload.github.com/{repo}/tar.gz/{rev}"
    with urllib.request.urlopen(url,timeout=40) as f:raw=f.read()
    wrote=0;seen=0
    with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as t:
        for m in t:
            name=m.name.partition("/")[2]
            if not m.isfile() or name not in tree:continue
            wanted,mode=tree[name];content=t.extractfile(m).read()
            blob=b"blob "+str(len(content)).encode()+b"\0"+content
            if hashlib.sha1(blob).hexdigest()!=wanted:continue
            seen+=1;out=root/"objects"/wanted[:2]/wanted[2:]
            if out.exists():continue
            out.parent.mkdir(exist_ok=True)
            tmp=out.with_name(out.name+"."+rev[:10]+".tmp")
            tmp.write_bytes(zlib.compress(blob,1))
            try:
                os.link(tmp,out);wrote+=1
            except FileExistsError:
                pass
            finally:
                tmp.unlink(missing_ok=True)
    return {"repo":repo,"sha":rev,"upstream":url,"archive_sha":sha(raw),"validated_blobs":seen,"written":wrote}
if __name__=="__main__":
    req=get(D/"keys.json");pairs={p['iid']:p for p in get(D/'git_pairs.json')}
    need=sorted({(r['repo'],pairs[r['iid']][s]) for r in req if r['key']['kind']=='text' and r['key']['scope']=='tests' for s in ('base','new')})
    with ThreadPoolExecutor(2) as pool:receipts=list(pool.map(fetch,need))
    save(D/"hydrated.json",receipts);print([(x['sha'][:8],x['validated_blobs']) for x in receipts])
