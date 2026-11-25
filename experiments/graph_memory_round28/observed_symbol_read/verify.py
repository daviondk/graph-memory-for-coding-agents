from common28 import *
if __name__=="__main__":
    r=read(D/"manifest.json")
    for x in r["files"]:
        p=D/x["name"];assert p.stat().st_size==x["bytes"] and sha(p)==x["sha"],p
    assert {p.name for p in D.iterdir() if p.is_file() and p.name!="manifest.json"}=={x["name"] for x in r["files"]}
    print("Verified",len(r["files"]),"files")

