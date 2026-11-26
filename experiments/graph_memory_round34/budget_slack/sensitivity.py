"""Descriptive audit of objective concentration and the deterministic upper bound."""
from pathlib import Path
import gzip,json,hashlib
from statistics import mean
import numpy as np
D=Path(__file__).resolve().parent
def read(name):
    p=D/name;b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def main():
    rr=list(read("train-query-weights.json.gz").values());rr=[r for r in rr if r["w"]["equal_flat"]>0]
    a=np.array([r["w"]["slack_sqrt"] for r in rr]);b=np.array([r["w"]["length_sqrt"] for r in rr])
    records={"train_active":len(rr),"pearson_slack_sqrt_length_sqrt":float(np.corrcoef(a,b)[0,1]),"seed13":{}}
    chosen=read("selection.json")["chosen"]
    for stage in ("dev","test"):
        rows=read(stage+"-proxy.json.gz");summary={}
        for name in dict.fromkeys(chosen.values()):
            v=[];miss=[]
            for r in rows.values():
                L=2048-r["P"]+1;A,y,native=r["order"]["13"][name]
                if L<=0:continue
                v.append(min(1,A/L));miss.append(1-y)
            summary[name]={"mean_capped_upper":mean(v),"observed_proxy_failure":mean(miss),
                          "A_zero":sum(x==0 for x in v),"budget_crossed":sum(x==1 for x in v)}
        records["seed13"][stage]=summary
    (D/"sensitivity.json").write_text(json.dumps(records,indent=2,sort_keys=True)+"\n",encoding="utf8")
if __name__=="__main__":main()