"""Use public sample per panel; local BM25 must reproduce published counts as an alignment check."""
import math, random, pickle, re
from collections import Counter
import pyarrow.parquet as pq
from run import ARMS
from features import compute
from io_utils import D,save,read,np,sha
STOP=set("""a about above after again against all also an and any are as at be because been before being
below between both but by can could did do does doing done down during each few for from further had has have
having how however if in into is it its itself just like make makes more most much must no nor not now of off
on once only or other our out over own same should so some such than that the their them then there these they
this those through to too under until up upon use used uses using very was way we were what when where which
while who whom why will with within without would you your called call calls code file files function functions
method methods defined define defines implemented implement happens work works find show tell""".split())
IDENTISH=re.compile(r"\x60([^\x60]+)\x60|\b([A-Za-z_][\w]*(?:(?:::|\.)[\w]+)+|[a-z]+_[\w]+|[A-Za-z]*[a-z][A-Z]\w*|[A-Z]{2,}\w*)\b")
REPORTED={"cff_easy":([108,401],[126,425]),"cff_hard":([65,245],[90,248]),"cfr_easy":([132,429],[149,439]),"cfr_hard":([106,289],[143,312])}
def bm_rank(query,candidates):
    out={}; docs=[c.lower() for c in candidates]
    for m in IDENTISH.finditer(query):
        t=(m.group(1) or m.group(2)).strip().lower()
        if t and len(t)<80 and t not in out:out[t]=3
    for t in re.findall(r"[A-Za-z]{4,}",query):
        t=t.lower()
        if t not in out and t not in STOP:out[t]=1
    terms=list(out)[:40];n=len(docs);avg=max(sum(map(len,docs))/max(n,1),1.)
    df={t:sum(t in d for d in docs) for t in terms}
    def score(d):
        norm=1.2*(.25+.75*len(d)/avg)
        return sum(out[t]*math.log(1+(n-df[t]+.5)/(df[t]+.5))*c*2.2/(c+norm) for t in terms if (c:=d.count(t)))
    return sorted(range(n),key=lambda i:(-score(docs[i]),i))
def main():
    assert sha(D/"models.pkl")==read("fit.json")["model_sha256"]
    with (D/"models.pkl").open("rb") as mf:models=pickle.load(mf)
    output={};order_file={}
    for p in sorted((D/"inputs").glob("*test*.parquet")):
        _,setting,_,level,_=p.stem.split("_");key=setting+"_"+level
        pf=pq.ParquetFile(p);n=pf.metadata.num_rows
        wanted=set(random.Random(f"20261003-python_{setting}-{level}").sample(range(n),500));labels=[];ranks=[];i=-1
        for batch in pf.iter_batches(batch_size=48,columns=["code","context"]):
            for row in batch.to_pylist():
                i+=1
                if i not in wanted:continue
                q="\n".join(row["code"].splitlines()[-3:]);ctx=row["context"];fv=compute(q,ctx,3)
                d={"sem_bm":bm_rank(q,ctx)}
                for a in ["flat3","transition3"]:
                    clf=models[a];d[a]=np.argsort(-clf.predict_proba(fv[:,ARMS[a][1]])[:,1],kind="stable").tolist()
                ranks.append([i,d])
        order_file[key]=ranks
    save("external_predictions.json",order_file)
    for key,ranks in order_file.items():
        setting,level=key.split("_");p=next((D/"inputs").glob(f"python_{setting}_test_{level}_*.parquet"))
        gold=pq.read_table(p,columns=["gold_snippet_index"]).column(0).to_pylist()
        vals={a:[sum(gold[i] in d[a][:k] for i,d in ranks) for k in (1,5)] for a in ranks[0][1]}
        vals["reported_bm"],vals["reported_semlith"]=REPORTED[key];output[key]=vals
    save("external_results.json",output)
if __name__=="__main__":main()
