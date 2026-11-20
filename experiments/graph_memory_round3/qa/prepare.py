import hashlib,json,re,gzip
from pathlib import Path
P=Path(__file__).resolve().parent
def sha(x):return hashlib.sha256(x if isinstance(x,bytes) else str(x).encode()).hexdigest()
def write(n,x): (P/n).write_text(json.dumps(x,ensure_ascii=True,indent=1),encoding='utf8')
def read(n):return json.loads((P/n).read_bytes())
def norm(t):return re.sub(r"\s+"," ",str(t)).strip()
def prepare():
    raw=read("upstream/locomo10.json");core=[];gold={}
    for r in raw:
        conv=r["conversation"];turns=[];name=r["sample_id"];dirs=[a for a in conv if re.fullmatch(r"session_\d+",a)]
        for f in sorted(dirs,key=lambda s:int(s.split("_")[-1])):
            for turn in conv[f]:
                caption=turn.get("blip_caption","")
                turns.append(dict(id=turn["dia_id"],speaker=turn["speaker"],text=norm(turn["text"]),caption=norm(caption),time=conv.get(f+"_date_time",""),session=f))
        queries=[]
        for j,a in enumerate(r["qa"]):
            key=f"{name}:{j}";queries.append(dict(id=key,text=a["question"]))
            gold[key]=dict(evidence=a.get("evidence",[]),cat=a["category"],answer=str(a.get("answer","")))
        core.append(dict(id=name,turns=turns,queries=queries))
    write("input.json",core);write("gold.json",gold)
if __name__=="__main__":prepare()
