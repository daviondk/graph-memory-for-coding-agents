from pathlib import Path
import hashlib,io,json,urllib.request,zipfile
ROOT=Path(__file__).resolve().parent;DST=ROOT/"upstream"
REV="d340bb2eaf3a81691820ef0683cd652753a9fa5a"
def main():
    url="https://codeload.github.com/iroiro147/dreambench-swe/zip/"+REV
    payload=urllib.request.urlopen(url,timeout=45).read()
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        for n in z.namelist():
            name=n.partition("/")[2]
            if not name or n.endswith("/"):continue
            f=DST/name;assert f.resolve().is_relative_to(DST);f.parent.mkdir(exist_ok=True,parents=True);f.write_bytes(z.read(n))
    (ROOT/"upstream.json").write_text(json.dumps(dict(sha=REV,url=url,archive_sha=hashlib.sha256(payload).hexdigest()),indent=2),encoding="utf8")
if __name__=="__main__":main()
