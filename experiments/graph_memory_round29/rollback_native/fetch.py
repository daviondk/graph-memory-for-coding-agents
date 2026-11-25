"""Obtain fixed upstream source and inert domain data; no shell scripts or data tool calls are executed."""
from pathlib import Path,PurePosixPath
from hashlib import sha256,sha1
from urllib.request import urlopen
import json,zipfile,io
D=Path(__file__).resolve().parent;P=Path("D:/CodexResearch/x20-r29-rollback");SRC=P/"upstream";REV="713724491b9bbc6e55f0f9d8723da0eb0766ced7";REPO="xiaoqi-7/memory-rollback"
def main():
    P.mkdir(exist_ok=True);SRC.mkdir(exist_ok=True)
    tree=json.loads(urlopen(f"https://api.github.com/repos/{REPO}/git/trees/{REV}?recursive=1").read());assert tree["sha"]==REV
    allowed={r["path"]:r["sha"] for r in tree["tree"] if r["type"]=="blob"}
    with urlopen(f"https://codeload.github.com/{REPO}/zip/{REV}",timeout=45) as fi:raw=fi.read(32*1024*1024)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for info in z.infolist():
            if info.is_dir():continue
            name=info.filename.split("/",1)[1];rel=PurePosixPath(name)
            assert not rel.is_absolute() and ".." not in rel.parts and name in allowed
            b=z.read(info);digest=sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest();assert digest==allowed[name],name
            p=SRC/rel;p.parent.mkdir(parents=True,exist_ok=True)
            if p.exists():assert p.read_bytes()==b,p
            else:p.write_bytes(b)
    print(len(allowed),"git blobs verified",sha256(raw).hexdigest())
if __name__=="__main__":main()

