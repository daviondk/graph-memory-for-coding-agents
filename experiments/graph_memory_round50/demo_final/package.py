"""Update the R49 offline candidate with the R50 manuscript and rebuild its internal receipt."""
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
import json
def h(b):return sha256(b).hexdigest()
D=Path(__file__).resolve().parent
SOURCE_DIGEST="4f418c3f88b6124f3813f0ba528dbbde1646bb0a2594b40cd1f0cab2aebd3028"

def main():
    source=D.parents[1]/"graph_memory_round49/stream_demo/candidate.zip"
    assert h(source.read_bytes())==SOURCE_DIGEST
    with ZipFile(source) as before:
        old={n:before.read(n) for n in before.namelist()}
    receipt=json.loads(old["CONTENT_SHA256.json"])
    assert {p:h(v) for p,v in old.items() if p!="CONTENT_SHA256.json"}==receipt
    old["paper.tex"]=(D/"paper.tex").read_bytes()
    old["paper.pdf"]=(D/"paper.pdf").read_bytes()
    additional=("\n## Manuscript measurements\n\nTable I reports terminal ISETrace retrieval and CPU timing on the same ordered packets. "
                "The feature-to-packet measurement begins with the materialized numeric pool and a native rank. "
                "Of 960 evidence-available questions at the midpoint, 901 remained after excluding the pilot, and at the eighth tool group 649 of 697 remained. Feature ablations refit the model with the same learner family, training protocol and first-fit selector. The original walkthrough and six working consoles illustrate the earlier source updates and integer and floating-point contracts described in the text. "
                "The benchmark uses the no-adjacency hybrid, while the trace console shows the primary graph-ranked example.\n")
    old["README.md"]+=additional.encode()
    content={n:h(v) for n,v in old.items() if n!="CONTENT_SHA256.json"}
    old["CONTENT_SHA256.json"]=(json.dumps(content,indent=2,sort_keys=True)+"\n").encode()
    with ZipFile(D/"candidate.zip","w") as dest:
        for n,data in sorted(old.items()):
            info=ZipInfo(n,(1980,1,1,0,0,0));info.compress_type=ZIP_DEFLATED
            info.external_attr=0o100644<<16
            dest.writestr(info,data)
    print("candidate",len(old),h((D/"candidate.zip").read_bytes()))
if __name__=="__main__":main()

