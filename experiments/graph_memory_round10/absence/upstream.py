"""Exercise intact upstream test functions from the project release artifacts."""
import concurrent.futures,hashlib,json,os,re,shutil,subprocess,sys,tarfile,urllib.request
from pathlib import Path
import xml.etree.ElementTree as ET
import experiment as e
D=e.D;dst=D/"upstream_execution"
spec={
 "tabulate":("test/test_output.py","test_grid_wide_characters"),
 "markdown-it-py":("tests/test_port/test_fixtures.py","test_linkify"),
 "networkx":("networkx/drawing/tests/test_pydot.py","test_hashable_pydot"),
 "fsspec":("fsspec/tests/test_compression.py","test_lz4_compression")}
FSS_COMMIT="0f76baaae4a227b085b18e8469e6cc1792a95ade"
FSS_BLOB="462b35904afbb7b6dbcb0162bd5b99e1fd83eea5"
def collect():
    specs={s["name"]:s for s in e.get(D/"sources.lock.json")}
    sources={}
    for p,(name,subset) in spec.items():
        rec=specs[p]["sdist"];root=dst/p/"code";root.mkdir(parents=True,exist_ok=True);entries={}
        if p=="fsspec":
            url="https://raw.githubusercontent.com/fsspec/filesystem_spec/"+FSS_COMMIT+"/"+name
            f=D/"upstream_tests"/p/name
            if not f.exists():f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(urllib.request.urlopen(url,timeout=40).read())
            b=f.read_bytes();assert hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()==FSS_BLOB
            entries[Path(name).name]=b
        else:
            url=rec["url"]
            with tarfile.open(D/"sources"/rec["file"]) as z:
                for m in z:
                    if not m.isfile():continue
                    rel=m.name.partition("/")[2]
                    if rel==name:entries[Path(rel).name]=z.extractfile(m).read()
                    if p=="tabulate" and rel=="test/common.py":entries["common.py"]=z.extractfile(m).read()
                    if p=="markdown-it-py" and rel.startswith("tests/test_port/fixtures/"):entries[rel.removeprefix("tests/test_port/")]=z.extractfile(m).read()
        for f,b in entries.items():
            file=root/f;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b)
        sources[p]={"version":specs[p]["version"],"url":url,"commit":FSS_COMMIT if p=="fsspec" else None,"selected_test":subset,"files":{k:e.sha(v) for k,v in entries.items()}}
    e.save(dst/"upstream-source-lock.json",sources)
def one(job):
    p,val=job;name,select=spec[p];root=dst/p/"code";out=dst/p/val;out.mkdir(exist_ok=True)
    target=root/Path(name).name
    # Exact node where a family sharing a prefix exists; testmodule importorskip can skip an entire module.
    if p=="markdown-it-py":args=[str(target)+"::"+select]
    else:args=[str(target),"-k",select]
    env=e.environment(D/"states"/p/val);cmd=[sys.executable,"-B","-m","pytest","-q","--disable-warnings","--confcutdir",str(root),"--junitxml",str(out/"tests.xml"),*args]
    res=subprocess.run(cmd,cwd=root,env=env,capture_output=True,timeout=100)
    (out/"pytest.log").write_bytes(res.stdout+res.stderr);xml=ET.parse(out/"tests.xml");units={}
    for t in xml.iter("testcase"):
        units[t.get("name")]=next((y for x,y in [("error","error"),("failure","failed"),("skipped","skipped")] if t.find(x) is not None),"passed")
    assert res.returncode in (0,5) and units and set(units.values())<={"skipped","passed"},(p,val,res.returncode,units,(res.stdout+res.stderr)[-500:])
    return {"project":p,"state":val,"rc":res.returncode,"units":units,"xml_sha":e.digest(out/"tests.xml")}
if __name__=="__main__":
    collect()
    with concurrent.futures.ThreadPoolExecutor(3) as pool:rows=list(pool.map(one,[(p,v) for p in spec for v in ["A","B","P"]]))
    e.save(dst/"results.json",rows);print([(x["project"],x["state"],len(x["units"]),set(x["units"].values())) for x in rows])
