"""Reapply exactly the frozen fitting/evaluation pipeline on the best non-learned dev reader."""
from collections import defaultdict
import experiment as ex
from prepare import *
def main():
    target=HERE/"strong";target.mkdir(exist_ok=True)
    first=read(HERE/"selection.json");arms=("bm25","dense_state","dense_addresses","rrf")
    anchor=max(arms,key=lambda k:first["dev"][k][0]);data=read(HERE/"features.json.gz")
    prior=read(RANKPATH)["rank"]
    for row in data.values():
        rank=np.array(row["ranks"][anchor]);n=len(rank)
        row["ranks"]["rrf"]=rank.tolist()
        X=np.array(row["x"]);X[:,0]=np.log1p(rank);row["x"]=X.tolist()
        shape=np.column_stack((-np.log(rank),1/rank,(n-rank)/max(n-1,1)))
        row["off"]=(shape@prior["coef"]+prior["intercept"]).tolist()
    (target/"PROTOCOL_RU.md").write_bytes((HERE/"STRONG_CONTROL_RU.md").read_bytes())
    p=target/"features.json.gz";save(p,data);save(target/"input.json",{"features":sha(p),"original":sha(HERE/"features.json.gz")})
    save(target/"anchor.json",{"name":anchor,"dev":{k:first["dev"][k][0] for k in arms},"source":sha(HERE/"selection.json"),"protocol":sha(HERE/"STRONG_CONTROL_RU.md")})
    ex.HERE=target;ex.defaultdict=defaultdict;ex.main()
    import grade_external as grade
    grade.HERE=target;grade.main()
if __name__=="__main__":main()
