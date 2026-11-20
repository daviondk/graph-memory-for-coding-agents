"""Natural released bytes. Fixed comparison before fetching second versions. No model or Git index."""
import concurrent.futures
import gzip
import io
import json
import random
from pathlib import Path
import sys
import subprocess
import tarfile
import time
from acquire import get, h, save, D
from experiment import decode, marker, RULES
from mcp import Client, dumpgz
from workspace_tools import stamp

UPDATES=[("8.1.8","src/click/"),("24.3.0","src/attr/"),("hypothesis-python-6.112.1","hypothesis-python/src/hypothesis/"),("6.0.3","lib/yaml/")]
ROOT=D/"natural";ROOT.mkdir(exist_ok=True)
def files(repo,tag,prefix):
    url="https://codeload.github.com/"+repo+"/tar.gz/refs/tags/"+tag
    raw=get(url);tar=tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz")
    by={}
    for m in tar.getmembers():
        p=m.name.partition("/")[2]
        if m.isfile() and p.startswith(prefix) and p.endswith(".py") and "test" not in p.lower().split("/"):
            by[p]=tar.extractfile(m).read()
    return by,{"url":url,"tag":tag,"sha256":h(raw)}
def eligible(b):
    try:s=b.decode()
    except UnicodeDecodeError:return False
    return "\r" not in s and "\t" not in s and 30<=len(s.splitlines())<=180 and s.endswith("\n")
def stage():
    metadata=json.loads((D/"fixtures.json").read_bytes());panel=[];refs=[]
    for record,(newtag,prefix) in zip(metadata,UPDATES):
        repo=record["repo"];old,a=files(repo,record["tag"],prefix);new,b=files(repo,newtag,prefix)
        assert a["sha256"]==record["source_sha256"]
        refs.append({"repo":repo,"old":a,"new":b})
        for p,x in sorted(old.items()):
            if not eligible(x):continue
            y=new.get(p)
            assert y is None or y.decode().endswith("\n")
            panel.append({"repo":repo,"file":p,"old":x.decode(),"new":y.decode() if y is not None else None,"sha_old":h(x),"sha_new":h(y) if y is not None else None})
    dumpgz(ROOT/"released_pairs.json.gz",panel);save("natural/sources.json",refs)
    return panel
def writer(script):
    for name,text in json.loads(Path(script).read_bytes()):
        Path(name).write_bytes(text.encode())
def main():
    panel=stage();paths={};stamps={};cmd=[]
    scratch=D/"scratch"/"natural";scratch.mkdir(exist_ok=True)
    sessions={k:Client(scratch,k) for k in ("native","full",*RULES)}
    rows=[];bills=[];initial=[]
    for i,r in enumerate(panel):
        if r["new"] is None:continue
        path=scratch/f"module_{i:03}.py";path.write_bytes(r["old"].encode());paths[i]=path
        for arm,client in sessions.items():
            reply,receipt=client.view(path.name)
            assert decode(reply,b"")==r["old"].encode()
            bills.append({"i":i,"arm":arm,"stage":"initial",**receipt})
            if arm in RULES:stamps[i,arm]=stamp(path,arm=="ntfs_change")
        initial.append((i,stamp(path,True)))
        if r["old"]!=r["new"]:cmd.append((str(path),r["new"]))
    job=scratch/"writer.json";job.write_text(json.dumps(cmd));subprocess.run([sys.executable,"-B",__file__,"write",str(job)],check=True)
    for i,r in enumerate(panel):
        if i not in paths:continue
        f=paths[i];old=r["old"].encode();gold=r["new"].encode();assert f.read_bytes()==gold
        final=stamp(f,True)
        order=list(sessions);random.Random(i+913).shuffle(order)
        for arm in order:
            client=sessions[arm];start=time.perf_counter_ns();hit=False
            if arm in RULES:
                current=stamp(f,arm=="ntfs_change")
                hit=all(current[k]==stamps[i,arm][k] for k in RULES[arm])
            if hit:text=marker(old)
            else:
                text,receipt=client.view(f.name,**({"full":True} if arm=="full" else {}))
                bills.append({"i":i,"arm":arm,"stage":"followup",**receipt})
            elapsed=time.perf_counter_ns()-start;restored=decode(text,old)
            rows.append(dict(i=i,arm=arm,repo=r["repo"],path=r["file"],hit=hit,native=int(not hit),correct=restored==gold,restored_sha=h(restored),old_sha=h(old),new_sha=h(gold),changed=old!=gold,payload=(0 if hit else len(gold)),view_bytes=len(text.encode()),elapsed_ns=elapsed,before=dict(initial)[i],after=final))
    for c in sessions.values():c.close()
    dumpgz(ROOT/"native_calls.json.gz",bills);dumpgz(ROOT/"scores.json.gz",rows)
    print(len(panel),len(cmd),len(rows),len(bills))
if __name__=="__main__":
    if len(sys.argv)>1:writer(sys.argv[2])
    else:main()
