from common import *
if __name__=="__main__":
    entries=read(D/"manifest.json")["files"]
    for v in entries:
        p=D/v["name"];assert p.stat().st_size==v["bytes"] and sha(p)==v["sha256"],p
    assert {x["name"] for x in entries}=={p.name for p in D.iterdir() if p.is_file() and p.name!="manifest.json"}
    print("Verified",len(entries),"files")

