"""Publish only prior source coordinates and native call IDs used by the packing policy."""
from setup_graph import ROOT,RUN,TR,CACHE,pilot,load,put
from collections import Counter
from pathlib import Path
import hashlib
def run():
    M={};dig=hashlib.sha256();keys={}
    for i in range(8):
        for f in sorted((CACHE/'projection').glob(f'{i}-*.json.gz')):
            rec=load(f);t=rec['t'];assert t not in M
            rows={x['item_id']:[x['metadata'].get('call_id'),x['metadata'].get('node_kind')] for x in rec['pool']}
            assert len(rows)==len(rec['pool']);M[t]=rows
            dig.update(f.name.encode()+b'\0'+bytes.fromhex(pilot.sha(f)))
    assert set(M)=={r['t'] for r in load(TR/'split.json.gz')['test']}
    p=ROOT/'candidate-call-map.json.gz';put(p,M)
    put(ROOT/'candidate-map-receipt.json',dict(trajectories=len(M),physical_candidates=sum(map(len,M.values())),source_projection=dig.hexdigest(),sha=pilot.sha(p)))
if __name__=='__main__':run()

