from pathlib import Path
import concurrent.futures,hashlib,json,urllib.request,shutil
from io_utils import D,save,sha
REV="8a7cf0c8942cc1aa066bf261839650ac55a2ff79"
def main():
    items=json.load(urllib.request.urlopen("https://huggingface.co/api/datasets/tianyang/repobench_python_v1.1/tree/"+REV+"/data",timeout=50))
    selected=[r for r in items if "/cross_file" in r["path"]]
    folder=D/"transfer_inputs";folder.mkdir(exist_ok=True)
    def get(r):
        name=r["path"].split("/")[-1];p=folder/name;u="https://huggingface.co/datasets/tianyang/repobench_python_v1.1/resolve/"+REV+"/"+r["path"]
        if not p.exists() or sha(p)!=r["lfs"]["oid"]:
            with urllib.request.urlopen(u,timeout=80) as f,p.with_suffix(".part").open("wb") as out:shutil.copyfileobj(f,out)
            assert sha(p.with_suffix(".part"))==r["lfs"]["oid"];p.with_suffix(".part").replace(p)
        return dict(path=name,sha256=sha(p),url=u)
    with concurrent.futures.ThreadPoolExecutor(3) as ex:out=list(ex.map(get,selected))
    save("transfer_sources.json",out)
if __name__=="__main__":main()
