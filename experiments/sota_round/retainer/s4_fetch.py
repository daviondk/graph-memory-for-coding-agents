"""Fetch and verify the two S4-FIFO submodules used by the original artifact."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import tarfile
import urllib.request
from fetch import HERE,RAW,fetch

ART="000095fc3c96a95ff1b9a19d101fb1411c7f4d54"
def main():
    base="https://api.github.com/repos/cacheMon/osdi26-s4-fifo/contents/"
    cache_rev=json.loads(fetch(base+"CacheLib?ref="+ART))["sha"]
    sim_rev=json.loads(fetch(base+"libCacheSim?ref="+ART))["sha"]
    assert sim_rev=="1f62efcf33e04b03a3e2ccaf2c40fb5ead918b4d" and cache_rev.startswith("72bb810")
    modelroot=RAW/"models";modelroot.mkdir(exist_ok=True)
    names=["MMS4FIFO.h","S4FIFOLightGBMPredictor.h","s4fifo_model/S4FIFOEnsemble.h","s4fifo_model/softmax.h"]+["s4fifo_model/model_%d.h"%i for i in range(5)]
    def get(name):
        url=f"https://raw.githubusercontent.com/williamnixon20/CacheLib/{cache_rev}/cachelib/allocator/"+name
        b=fetch(url); path=modelroot/name;path.parent.mkdir(exist_ok=True,parents=True);path.write_bytes(b)
        return name,dict(url=url,sha256=hashlib.sha256(b).hexdigest())
    with ThreadPoolExecutor(5) as pool:models=dict(pool.map(get,names))
    h=(modelroot/"MMS4FIFO.h").read_text(encoding="utf8")
    fragment=h[h.index("struct S4FIFOFeatureVector"):h.index("// Prediction callback function type")]
    (modelroot/"types.h").write_text("constexpr int kS4FIFODefaultBuckets=20, kS4FIFOMaxBuckets=64;\n"+fragment,encoding="utf8")
    simurl=f"https://codeload.github.com/haochengxia/libCacheSim/tar.gz/{sim_rev}"
    b=fetch(simurl); root=RAW/"libcache-src";root.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(b),mode="r:gz") as f:
        for m in f.getmembers():
            if m.isfile():
                path=root.joinpath(*m.name.split("/")[1:])
                assert path.resolve().is_relative_to(root.resolve())
                path.parent.mkdir(exist_ok=True,parents=True);path.write_bytes(f.extractfile(m).read())
    (HERE/"s4_sources.json").write_text(json.dumps(dict(artifact=ART,sim_revision=sim_rev,sim_url=simurl,sim_archive_sha256=hashlib.sha256(b).hexdigest(),cachelib_revision=cache_rev,models=models),indent=2),encoding="utf8")
if __name__=="__main__":main()
