import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

for variable in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS","NUMEXPR_NUM_THREADS","RAYON_NUM_THREADS"):
    os.environ[variable] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
ROOT = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("MD2D_CACHE","D:/CodexResearch/x20-r23-multidoc2dial"))
MODEL = CACHE/"model"
WEIGHTS = ROOT.parents[1]/"graph_memory_round20/fine_train/model.json"
sys.path.insert(0, str(CACHE/"libs"))
from tokenizers import Tokenizer

def sha(b):
    return hashlib.sha256(b).hexdigest()

def checksum(path):
    return sha(path.read_bytes())

def short(x):
    return sha(x.encode())[:20]

def save(path,x):
    raw = (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    path.write_bytes(gzip.compress(raw,compresslevel=5,mtime=0) if path.suffix==".gz" else raw)
    return checksum(path)

def read(path):
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix==".gz" else raw)

def source(name):
    assert checksum(CACHE/"source.zip")=="f0c034c249663d7b3cb08b19cf2cc2c3d101372485be982621d4711931a1ce00"
    with zipfile.ZipFile(CACHE/"source.zip") as z:
        return json.loads(z.read("multidoc2dial/multidoc2dial_"+name+".json"))

def tok():
    t=Tokenizer.from_file(str(MODEL/"tokenizer.json"))
    t.no_padding()
    t.no_truncation()
    return t

def packets():
    t=tok()
    domains=source("doc")["doc_data"]
    docs=[];blocks=[]
    for domain in sorted(domains):
        for doc_id,doc in sorted(domains[domain].items()):
            ident=len(docs)
            body=doc["doc_text"]
            enc=t.encode(body,add_special_tokens=False)
            # Adjacent fragments partition the whole source, including intervening spaces.
            def bounds(i):
                return 0 if i==0 else len(body) if i>=len(enc.ids) else enc.offsets[i][0]
            docs.append([short(domain+"\x1f"+doc_id),doc["title"],body])
            for i in range(0,len(enc.ids),256):
                first=len(blocks)
                end=min(i+256,len(enc.ids))
                borders=[bounds(j) for j in range(i,end,64)]+[bounds(end)]
                blocks.append({"doc":ident,"a":bounds(i),"b":bounds(end),"parent":first,"coarse":True})
                for x,y in zip(borders,borders[1:]):
                    blocks.append({"doc":ident,"a":x,"b":y,"parent":first,"coarse":False})
    dialogs=source("dial_validation")["dial_data"]
    qs=[]
    for domain in sorted(dialogs):
        for dialog in dialogs[domain]:
            turns=dialog["turns"]
            eligible=[i for i in range(1,len(turns)) if turns[i-1]["role"]=="user" and turns[i]["role"]=="agent"]
            if not eligible:continue
            dial=dialog["dial_id"]
            def name(i):
                return dial+"\x1f"+str(turns[i]["turn_id"])
            selected=min(eligible,key=lambda i:sha(name(i).encode()))
            prefix=[r["utterance"] for r in reversed(turns[max(0,selected-3):selected])]
            qs.append([short(name(selected)),short(dial)," [SEP] ".join(prefix)])
    assert len(docs)==488 and len(qs)==661 and len({q[1] for q in qs})==len(qs)
    return {"documents":docs,"blocks":blocks,"q":sorted(qs)}

def render(unit,documents):
    doc,a,b=unit["doc"],unit["a"],unit["b"]
    return f"[D{doc:03d} {a}:{b}]\n"+documents[doc][2][a:b]

def get_views():
    lock=read(ROOT/"input-lock.json")
    path=CACHE/"view.json.gz"
    assert checksum(path)==lock["view"] and checksum(WEIGHTS)==lock["fine_train_model"]
    assert checksum(ROOT/"PROTOCOL_RU.md")==lock["protocol"]
    return read(path)

if __name__=="__main__":
    view=packets()
    v=save(CACHE/"view.json.gz",view)
    span=0
    for j,(_,_,body) in enumerate(view["documents"]):
        w=[u for u in view["blocks"] if u["doc"]==j and not u["coarse"]]
        assert w[0]["a"]==0 and w[-1]["b"]==len(body)
        assert all(a["b"]==b["a"] for a,b in zip(w,w[1:]))
        span+=len(body)
    inputs={p.name:checksum(p) for p in sorted(MODEL.iterdir()) if p.is_file()}
    summary=dict(source=checksum(CACHE/"source.zip"),view=v,q=len(view["q"]),docs=len(view["documents"]),coarse=sum(x["coarse"] for x in view["blocks"]),fine=sum(not x["coarse"] for x in view["blocks"]),characters=span,
                 model_files=inputs,revision="ffb93f3bd4047442299a41ebb6fa998a38507c52",fine_train_model=checksum(WEIGHTS),
                 source_url="https://doc2dial.github.io/multidoc2dial/file/multidoc2dial.zip",protocol=checksum(ROOT/"PROTOCOL_RU.md"),preparer=checksum(ROOT/"common.py"))
    assert summary["protocol"]=="6498ee8f5bb278effe6c7b43892d3ffe0dccd97aec1267ad31e89e5a0ac2d087"
    print("input lock",save(ROOT/"input-lock.json",summary),summary["coarse"],summary["fine"],flush=True)
