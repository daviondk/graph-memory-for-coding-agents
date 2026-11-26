from pathlib import Path
import hashlib,json,sys
from zipfile import ZipFile
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent))
import prepare as c
from prepare import PARENT,WORK,ZIP,SOURCE,read,save,hashfile
RUN=Path("D:/CodexResearch/x20-r52-global-supp-reader")
def get(f):return read(D/f)
def put(f,obj):save(D/f,obj)
def main():
    RUN.mkdir(exist_ok=True,parents=True)
    parent=read(PARENT/"prediction-seal.json")
    assert all(hashfile(PARENT/f)==digest for f,digest in parent["local"].items())
    preds=read(PARENT/"predictions.json.gz");names=read(PARENT/"chosen-titles.json.gz")
    pool=read(PARENT/"novelty.json")["ever_unseen_ids"]
    sample=read(D.parent/"sample.json.gz");keys=parent["arms"]
    profiles={};diff=[];targets=set()
    def add_row(name,q,r,arms):
        profiles[name+"|"+q]=dict(q=q,seed=r["seed"],arms=arms)
        targets.update(arms.values())
    for q in pool:
        row=preds[q];at=lambda arm:row["choices"][keys.index(arm)]
        if q in sample:
            if row["learned_direct"]:
                assert row["direct_gate"][1]>0 and at("learned_dev")==row["direct_gate"][0]
                other=row["direct_gate"][0]
            else:
                assert at("learned_dev")==at("href_first")
                other=at("text_first")
            add_row("fallback",q,row,dict(learned_href=at("learned_dev"),learned_literal=other))
        if at("learned_dev")!=at("coord_cautious"):
            diff.append(q)
            add_row("census",q,row,{a:at(a) for a in c.ARMS})
    assert len(diff)==10 and len(profiles)==522 and len(set(sample))==512
    put("choices.json.gz",profiles)
    put("registration.json",dict(protocol=hashfile(D/"PROTOCOL_RU.md"),code=hashfile(Path(__file__)),parent=hashfile(PARENT/"prediction-seal.json"),choices=hashfile(D/"choices.json.gz"),sample=hashfile(D.parent/"sample.json.gz"),pool=hashfile(PARENT/"novelty.json"),discordant=sorted(diff)))
    other=read(c.RUN/"texts.json.gz")
    assert hashfile(c.RUN/"texts.json.gz")==read(D.parent/"texts-seal.json")["texts"]
    docs={str(k):other["second"][str(k)] for k in targets if str(k) in other["second"]}
    missing={k for k in targets if str(k) not in docs}
    if missing:
        with ZipFile(ZIP) as archive,archive.open(SOURCE["member"]) as stream:
            for i,line in enumerate(stream):
                if i not in missing:continue
                obj=json.loads(line);assert [int(obj["id"]),obj["title"]]==names[str(i)]
                docs[str(i)]=[obj["title"]," ".join(obj["sentences"])]
                missing.remove(i)
                if not missing:break
    assert len(docs)==len(targets)
    qtext=read(WORK/"questions.json.gz");opened=read(WORK/"opened.json.gz")
    seeds={str(v["seed"]) for v in profiles.values()}
    raw=dict(first={k:[opened[k]["title"],opened[k]["prefix"]] for k in seeds},second=docs,
             questions={r["q"]:qtext[r["q"]] for r in profiles.values()})
    save(RUN/"texts.json.gz",raw)
    put("texts-seal.json",dict(texts=hashfile(RUN/"texts.json.gz"),targets=len(docs),source_zip=SOURCE["zip_sha256"],
        source_main_texts=hashfile(c.RUN/"texts.json.gz"),registration=hashfile(D/"registration.json")))
    print("Supplemental input assembled",len(profiles),len(docs),flush=True)
if __name__=="__main__":main()
