"""Evaluate a frozen, one-read policy on the author-maintained 2Wiki development split."""
import json
from pathlib import Path
import subprocess
import sys
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parent
R31=ROOT.parents[1]/"graph_memory_round31"
sys.path.insert(0,str(R31/"observed_links"))
from predict import ReadOne, choose, catalog, ranks, words, tie, E5, Tokenizer, sha, put, get

REV="612bc5039a457880d9e7d84c3b0a4cf154b70e4f"
URL=f"https://huggingface.co/datasets/xanhho/2WikiMultihopQA/resolve/{REV}/dev.parquet"
CACHE=Path("D:/CodexResearch/x20-r32-2wiki")
SRC=CACHE/"dev.parquet"

class Evidence(ReadOne):
    def open(self,j):
        self.snippet,cost=super().open(j)
        return self.snippet,cost

def local_static(question,titles,snippet,seed,mentions):
    seq,idf,search=catalog(question,titles)
    initial=ranks(search(question));query={w for w in set(words(question))-set(seq[seed]) if len(w)>2}
    text=words(snippet)
    def order(j):
        positions=mentions.get(str(j),[])
        scores=[sum(idf.get(t,1.) for t in sorted(query&set(text[max(0,i-12):i+len(seq[j])+12]))) for i in positions]
        return (not positions,-max(scores,default=0),initial[j],j)
    return min((j for j in initial if j!=seed),key=order)

def main():
    CACHE.mkdir(exist_ok=True)
    if not SRC.exists():
        tmp=SRC.with_suffix(".download")
        subprocess.run(["curl.exe","-fsSL","--retry","2","-o",str(tmp),URL],check=True)
        tmp.replace(SRC)
    plan={"source":sha(SRC),"url":URL,"protocol":sha(ROOT/"PROTOCOL_RU.md"),"policy":sha(Path(__file__)),
          "previous":sha(R31/"observed_links/predict.py"),"tokenizer":sha(E5/"tokenizer.json")}
    put(ROOT/"plan.json",plan)
    tok=Tokenizer.from_file(str(E5/"tokenizer.json"));preds={}
    for batch in pq.ParquetFile(SRC).iter_batches(batch_size=256,columns=["_id","question","context"]):
        for item in batch.to_pylist():
            q=item["_id"];question=item["question"];context=json.loads(item["context"])
            idx=sorted(range(len(context)),key=lambda i:tie(q+"|"+context[i][0]))
            titles=[context[i][0] for i in idx];reader=Evidence(idx,[c[1] for c in context],tok)
            rec=choose(question,titles,reader,qid=q);seed=rec["seed"]
            rec["next"]["local_static"]=local_static(question,titles,reader.snippet,seed,rec["mentions"])
            assert q not in preds and reader.read_ids==[seed]
            preds[q]={"order":idx,"seed":seed,"next":rec["next"],"tokens":rec["tokens"],"n_links":len(rec["mentions"])}
    put(ROOT/"predictions.json.gz",preds)
    put(ROOT/"seal.json",{"n":len(preds),"predictions":sha(ROOT/"predictions.json.gz"),"plan":sha(ROOT/"plan.json")})
if __name__=="__main__":main()
