"""Descriptive comparison with the parent experiments' no-eviction BM25 reader."""
from features import ROOT,ONLINE,load,save
from transfer_write import DEV
from score import ci
def main():
    our={(r["split"],r["q"]):r for r in load(ROOT/"transfer-outcomes.json.gz")};out={}
    for stage,path in (("test",ONLINE/"outcomes.json.gz"),("dev",DEV/"outcomes.json.gz")):
        comp=[dict(t=r["t"],a={"full":our[stage,r["q"]]["a"]["tokens/full"],"unbounded":r["a"]["all"]}) for r in load(path)]
        out[stage]={k:sum(r["a"][k][3] for r in comp) for k in ("full","unbounded")}
        out[stage]["read_delta"]=ci(comp,("full","unbounded"),3);out[stage]["n"]=len(comp)
    save(ROOT/"unbounded-reference.json",out);print(out)
if __name__=="__main__":main()
