"""Run the upstream sentence splitter on the sealed, label-free 48-article dev text."""
import gzip,hashlib,json,os
from pathlib import Path
from importlib.metadata import version
D=Path(__file__).resolve().parent;P=Path("D:/CodexResearch/x20-r28-squad-qa")
os.environ["NLTK_DATA"]="D:/CodexResearch/x20-r27-sentences/bundled-nltk-copy"
from llama_index.core import Document
from llama_index.core.node_parser.text.sentence_window import SentenceWindowNodeParser
from llama_index.core.utils import globals_helper
import llama_index.core.node_parser.text.sentence_window as module
def main():
    view=Path("D:/CodexResearch/x20-r26-squad-qa/blind-input.json.gz")
    read=lambda p:json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    published=read(D.parents[1]/"graph_memory_round27/sentence_window/native-receipt.json")
    assert sha(Path(module.__file__))==published["parser"]
    assert sha(view)==read(D.parents[1]/"graph_memory_round26/directional_answers/input-lock.json")["view"]
    parser=SentenceWindowNodeParser.from_defaults();punkt=globals_helper.punkt_tokenizer
    assert parser.window_size==3 and version("llama-index-core")=="0.14.26" and len(punkt._params.abbrev_types)==0
    spans={}
    for t,s in read(view)["docs"].items():
        a=list(punkt.span_tokenize(s))
        rs=[(l,a[i+1][0] if i+1<len(a) else len(s)) for i,(l,r) in enumerate(a)]
        nodes=parser.get_nodes_from_documents([Document(text=s)])
        for i,(node,(l,r)) in enumerate(zip(nodes,rs,strict=True)):
            val=" ".join(s[x:y] for x,y in rs[max(0,i-3):i+4]);assert node.text==node.metadata["original_text"]==s[l:r] and node.metadata["window"]==val
        spans[t]=rs
    p=D/"sentence-index.json.gz";p.write_bytes(gzip.compress(json.dumps(spans,sort_keys=True,separators=(",",":")).encode(),mtime=0))
    v=dict(n=len(spans),sentences=sum(map(len,spans.values())),index=sha(p),plan=sha(D/"PROTOCOL_RU.md"),code=sha(Path(__file__)),
           parser=sha(Path(module.__file__)),native_version=version("llama-index-core"),view=sha(view))
    (D/"sentence-seal.json").write_text(json.dumps(v,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(v["n"],v["sentences"])
if __name__=="__main__":main()
