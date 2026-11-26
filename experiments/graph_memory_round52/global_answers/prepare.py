"""Freeze a hash sample and recover only the selected actual second articles from the ZIP."""
from pathlib import Path
import hashlib,json,sys
from zipfile import ZipFile
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"global_policy"))
from seal_policy import BASE,WORK,OUTPUTS,read,save,hashfile
from corpus import ZIP,SOURCE
RUN=Path("D:/CodexResearch/x20-r52-global-reader")
ARMS=("primary_href","primary_text","href_first")
def load(n):return read(HERE/n)
def put(n,v):save(HERE/n,v)
def prepare():
    RUN.mkdir(exist_ok=True,parents=True)
    policy=HERE.parent/"global_policy"
    seal=read(policy/"prediction-seal.json")
    assert seal["local"]["predictions.json.gz"]==hashfile(policy/"predictions.json.gz")
    assert seal["local"]["chosen-titles.json.gz"]==hashfile(policy/"chosen-titles.json.gz")
    pred=read(policy/"predictions.json.gz");titles=read(policy/"chosen-titles.json.gz")
    opened=read(WORK/"opened.json.gz");qtext=read(WORK/"questions.json.gz")
    verified=read(BASE/"opening.json")
    assert verified["opened"]==hashfile(WORK/"opened.json.gz")
    assert read(BASE/"source.json")["questions"]==hashfile(WORK/"questions.json.gz")
    ids=sorted(pred,key=lambda k:hashlib.sha256(("r52-global-reader-v1|"+k).encode()).hexdigest())[:384]
    selection={k:dict(seed=pred[k]["seed"],second={a:pred[k]["choices"][OUTPUTS.index(a)] for a in ARMS}) for k in ids}
    put("selection.json.gz",selection)
    put("registration.json",dict(protocol=hashfile(HERE/"PROTOCOL_RU.md"),parent=hashfile(policy/"prediction-seal.json"),
         selection=hashfile(HERE/"selection.json.gz"),source_code=hashfile(Path(__file__)),n=len(ids)))
    targets={t for z in selection.values() for t in z["second"].values()}
    docs={};source=read(BASE/"source.json")
    assert ZIP.stat().st_size==SOURCE["compressed_archive"] and source["archive"]==SOURCE["zip_sha256"]
    print("Verifying ZIP",flush=True);assert hashfile(ZIP)==source["archive"]
    with ZipFile(ZIP) as z,z.open(SOURCE["member"]) as stream:
        for row,line in enumerate(stream):
            if row not in targets:continue
            obj=json.loads(line);wiki,title=titles[str(row)]
            assert str(obj["id"])==str(wiki) and obj["title"]==title
            docs[str(row)]=[title," ".join(obj["sentences"])]
            if len(docs)==len(targets):break
    assert len(docs)==len(targets)
    first={str(v["seed"]):[opened[str(v["seed"])]["title"],opened[str(v["seed"])]["prefix"]] for v in selection.values()}
    raw=dict(first=first,second=docs,questions={q:qtext[q] for q in ids})
    save(RUN/"texts.json.gz",raw)
    put("texts-seal.json",dict(texts=hashfile(RUN/"texts.json.gz"),questions=len(ids),unique_second=len(docs),
        first=len(first),zip=source["archive"],member=SOURCE["member"],selection=hashfile(HERE/"selection.json.gz")))
    print("Retrieved actual bodies",len(docs),flush=True)
if __name__=="__main__":prepare()
