import numpy as np
import json
from analyze import read,crossed,D,seeds

def main():
    rows=[r for i in range(8) for r in read(D/f"outcomes-{i}.json.gz") if r["cut"]==50 and r["eligible"] and not r["pilot"]]
    _,cl=np.unique([r["t"] for r in rows],return_inverse=True)
    res={}
    for left,right in [("graph_dp","dense_firstfit"),("graph_firstfit","dense_firstfit"),("graph_dp","graph_strict")]:
        a=np.array([[r["arms"][str(s)][left] for s in seeds] for r in rows])
        b=np.array([[r["arms"][str(s)][right] for s in seeds] for r in rows])
        z=a-b
        res[left+"/"+right]=dict(delta=z.mean(axis=(0,1)).tolist(),ci=crossed(z,cl,seeds))
    (D/"controls.json").write_text(json.dumps(res,indent=2)+"\n",encoding="utf8")
    print(res)

if __name__=="__main__":main()

