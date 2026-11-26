"""Verify the label and query mapping against the standalone canonical code2test release, streaming only its manifest member."""
from contextlib import closing
import hashlib
import json
import tarfile
from urllib.request import urlopen
from source import ARC,HERE,read,save
HF="https://huggingface.co/datasets/eyuansu71/agent_retrieval_bench/resolve/5901e1ee3aff048290db72edf9c63bc498b79ea3/releases/v2_code2test/agent_retrieval_bench_v2_code2test.tar.zst"
SAMPLE_SHA="712b2699d3f963c2f940688ae5248304263c4ecda1b3831b2801c95712a50b85"
def source(stream):
    for m in stream:
        if m.name.endswith("/samples.jsonl"):
            b=stream.extractfile(m).read()
            return b,{r["id"]:r for r in map(json.loads,b.splitlines()) if r["task_type"]=="code2test"}
    raise RuntimeError("No samples member")
def main():
    with tarfile.open(ARC,"r|zst") as t:_,legacy=source(t)
    with closing(urlopen(HF,timeout=50)) as stream:
        with tarfile.open(fileobj=stream,mode="r|zst") as t:b,standalone=source(t)
    digest=hashlib.sha256(b).hexdigest()
    assert digest==SAMPLE_SHA and set(legacy)==set(standalone)==set(read(HERE/"roster.json"))
    keys=("repo","base_commit","query","gold")
    for q,r in standalone.items():
        for k in keys:assert r[k]==legacy[q][k],(q,k)
    out=dict(source_url=HF,bytes_in_samples=len(b),samples_sha256=digest,matching_ids=len(standalone),identical_fields=list(keys))
    save(HERE/"canonical-v2.json",out)
    print(out)
if __name__=="__main__":main()
