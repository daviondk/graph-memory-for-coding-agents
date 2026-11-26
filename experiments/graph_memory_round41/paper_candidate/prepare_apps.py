"""Extract only the two reviewed runtimes from pinned experiment archives."""
from hashlib import sha256
import json
from pathlib import Path
import zipfile

D=Path(__file__).resolve().parent
R40=D.parents[1]/"graph_memory_round40"
SOURCES={
    "trace":("demo_revision/ICDE-demo-revision.zip","8248e2ff025c26d620520840059d6f9e716951bb05e9b7b33d70659c057a02a4",
             ("launcher.py","console.html","runtime/reader.py","runtime/reader.sqlite","runtime/grader.sqlite","runtime/DATA_SOURCE.md")),
    "code":("edit_demo/code-edit-demo.zip","b5930d4173aae9952e39a94e85af205e2d1e0c8e91f87526bdfb59fb9d8c5407",
            ("app.py","index.html","reader.sqlite","witness.sqlite"))}
def main():
    hashes={}
    for name,(file,expected,names) in SOURCES.items():
        archive=R40/file
        assert sha256(archive.read_bytes()).hexdigest()==expected
        with zipfile.ZipFile(archive) as z:
            for member in names:
                data=z.read(member);path=D/"apps"/name/member
                path.parent.mkdir(parents=True,exist_ok=True)
                if path.exists():assert path.read_bytes()==data
                else:path.write_bytes(data)
                hashes[path.relative_to(D).as_posix()]=sha256(data).hexdigest()
    (D/"app-inputs.json").write_text(json.dumps(hashes,sort_keys=True,indent=2)+"\n",encoding="utf8")
if __name__=="__main__":main()

