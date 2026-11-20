"""Obtain only the author archive central-directory and Java retrieval members via byte ranges."""
from pathlib import Path
import io, json, zipfile, requests, hashlib, time
D=Path(__file__).resolve().parent
URL="https://drive.usercontent.google.com/download?id=1HvFFnOybTKEJCrEypWh4ftmW6DZBaiK_&export=download&confirm=t"
class Remote(io.RawIOBase):
    def __init__(self):
        self.s=requests.Session();self.n=1192910469;self.pos=0
    def seekable(self):return True
    def seek(self,off,mode=0):
        self.pos=[0,self.pos,self.n][mode]+off;return self.pos
    def tell(self):return self.pos
    def read(self,sz=-1):
        if sz<0:sz=self.n-self.pos
        sz=min(sz,self.n-self.pos)
        if sz<=0:return b""
        lo,hi=self.pos,self.pos+sz-1
        for j in range(4):
            try:
                rr=self.s.get(URL+f"&rangeKey={lo}-{hi}-{j}",headers={"Range":f"bytes={lo}-{hi}"},timeout=90)
                assert rr.status_code==206 and rr.headers["Content-Range"].startswith(f"bytes {lo}-{hi}/"),(rr.status_code,rr.headers,len(rr.content))
                assert len(rr.content)==sz
                self.pos+=sz;return rr.content
            except Exception:
                if j==3:raise
                time.sleep(1+j)
def main():
    with zipfile.ZipFile(Remote()) as z:
        rows=[(x.filename,x.compress_size,x.file_size,x.CRC) for x in z.infolist()]
        (D/"archive_members.json").write_text(json.dumps(rows,indent=1),encoding="utf8")
        for name,comp,size,crc in rows:
            if "retrieval" in name.lower():
                print(name,comp,size,flush=True)
                if "java" in name and size:
                    dest=D/"inputs"/("archive_"+Path(name).name)
                    if dest.exists():continue
                    buf=z.read(name)
                    dest.write_bytes(buf)
                    print("Downloaded",dest.name,hashlib.sha256(buf).hexdigest(),flush=True)
if __name__=="__main__":main()
