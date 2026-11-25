"""Get public inputs directly; never execute code in the tarball at extraction time."""
import hashlib, io, tarfile, urllib.request
from pathlib import Path
D=Path("D:/CodexResearch/x20-r25-qasper")
ARCHIVE="https://qasper-dataset.s3.us-west-2.amazonaws.com/qasper-test-and-evaluator-v0.3.tgz"
QWT="https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/resolve/cdbee75f17c01a7cc42f958dc650907174af0554/tokenizer.json"
def put(path,data,digest=None):
    if digest and hashlib.sha256(data).hexdigest()!=digest:raise ValueError(path)
    if path.exists() and path.read_bytes()!=data:raise ValueError("different existing file "+str(path))
    if not path.exists():path.write_bytes(data)
def get(url):
    with urllib.request.urlopen(url,timeout=60) as f:return f.read()
def main():
    D.mkdir(exist_ok=True)
    archive=get(ARCHIVE)
    put(D/"test.tgz",archive,"72a52a41193e2838b8074f80ac074b94f956b84886c36a61c58a7df4171bdd72")
    with tarfile.open(fileobj=io.BytesIO(archive),mode="r:gz") as t:
        for name in ("qasper-test-v0.3.json","qasper_evaluator.py","README-test.md"):
            entry=t.getmember(name)
            assert entry.isfile()
            put(D/name,t.extractfile(entry).read())
    put(D/"qwen-tokenizer.json",get(QWT),"aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4")
if __name__=="__main__":main()
