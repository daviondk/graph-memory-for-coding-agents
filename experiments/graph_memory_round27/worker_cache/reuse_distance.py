"""Independently predict cache misses using distinct references since the last read."""
import gzip
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def verify():
    schedule=json.loads((ROOT/"schedule.json").read_bytes())["order"]
    rows=json.loads(gzip.decompress((ROOT/"responses.json.gz").read_bytes()))
    observed={(m,c,r,q):miss for rep,m,c,r,sid,q,w,win,wire,body,miss,ns,rpc in rows if rep==0}
    output={}
    for route,column in (("affine",2),("rotate",3)):
        visited=[[] for _ in range(4)]
        distances=[]
        for entry in schedule:
            sid,q=entry[:2];slot=entry[column]
            history=visited[slot]
            distance=None
            if sid in history:
                last=max(i for i,s in enumerate(history) if s==sid)
                distance=len(set(history[last+1:]))
            history.append(sid);distances.append(distance)
            for cap in (1,4,8):
                for method in ("raw_cache","term_cache"):
                    assert observed[method,cap,route,q]==int(distance is None or distance>=cap)
            assert observed["shared_sql",4,route,q]==1
        output[route]={str(k):sum(d==k for d in distances) for k in dict.fromkeys(distances)}
    return output
if __name__=="__main__":
    print(json.dumps(verify(),sort_keys=True,indent=2))

