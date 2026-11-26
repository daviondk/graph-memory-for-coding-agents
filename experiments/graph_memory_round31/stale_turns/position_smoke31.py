"""Exercise source-boundary and exact-budget handling on 6 public ID-hash-selected completed blind cases."""
from position31 import render,QWT,Tokenizer,source
from base31 import D,P,read,save,h,sha,DATA,Path
def main():
    pr=read(D/"progress.json");shards=list((P/"shards"/pr["config"]).glob("*.json.gz"));tok=Tokenizer.from_file(str(QWT));num=0
    chosen=sorted(shards,key=lambda x:h("r31-boundary-smoke/"+x.name))[:6]
    for shard in chosen:
        row=read(shard);c=row["case"];hist={s["id"]:s for s in read(DATA/"history"/(c+".json.gz"))["sources"]};ss={}
        for item in row["out"].values():
            for z in item["turn_pair"]:
                sid=z["source"]
                if sid not in ss:ss[sid]=source(hist[sid],tok)
                for m in ("first","last"):
                    v=render(ss[sid],m,z["native"],tok);assert v["native"]==z["native"];num+=1
    save(D/"position-smoke.json",dict(scope=[p.name.split(".")[0] for p in chosen],checks=num,phase="before scoring",code=sha(Path(__file__))))
if __name__=="__main__":main()
