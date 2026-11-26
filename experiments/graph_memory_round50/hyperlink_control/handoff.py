"""Emit explicit second-document indices for the visible-only handoff, without labels."""
from common import *
def main():
    seals=read(D/"clip-seal.json")
    out={}
    for split in CONFIG:
        basefile=D/f"forecast-{split}.json.gz";fp=D/f"clip-{split}.json.gz"
        assert sha(fp)==seals["predictions"][split]
        assert sha(basefile)==read(D/"prediction_seal.json")["subsets"][split]["predictions"]
        prior=read(basefile);clipped=read(fp);data={}
        for q,r in prior.items():
            eligible,href,second=clipped[q];sort=r["sort"];joint=set(href)|set(r["text_edges"])
            union=next((j for j in sort if j in joint),sort[0])
            data[q]={"seed":r["seed"],"href":second,"union":union,"text":r["choices"]["text"],"lex":r["choices"]["lex"]}
        p=D/f"handoff-{split}.json.gz";write(p,data)
        out[split]={"file":p.name,"sha256":sha(p),"rows":len(data),"visible_clip":sha(fp),"frozen_numeric_rows":sha(basefile)}
    write(D/"handoff.json",{"subsets":out,"selection_code":sha(Path(__file__)),"prediction_seal":sha(D/"prediction_seal.json"),
          "clip_seal":sha(D/"clip-seal.json"),"indices":"original zero-based catalogue indices; seed first, named methods second"})
    print(sha(D/"handoff.json"));print(json.dumps(out))
if __name__=="__main__":main()

