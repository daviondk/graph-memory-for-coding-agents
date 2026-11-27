"""Direct aggregate of entirely resident incidences after a certified empty residual."""
from collections import Counter
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import argparse
import control_fast
from residual import BARE, POST, EVENT, Residual, best, contains, unpack, v, load, save, prepare
HERE=Path(__file__).resolve().parent
core=control_fast.core
EMPTY=bytes((BARE,))
class ResidentHit(Residual):
    def __init__(self,db,cap,allow_present):
        super().__init__(db,cap,"residual_only")
        self.allow_present=allow_present

    def _query(self,f,tie,prior):
        key=(POST,f)
        if f in self.known and f not in self.hot.lost_shared:
            return super()._query(f,tie,prior)
        cache=self.cache.items
        packet=cache.get(key)
        if packet is None or packet[0]!=BARE:
            return super()._query(f,tie,prior)
        hot=self.hot.incident.get(f,())
        if packet!=EMPTY:
            if not self.allow_present or any(j not in hot and (EVENT,j) not in cache for j in unpack(packet[1:])):
                return super()._query(f,tie,prior)
        scores=Counter()
        resident=[]
        for j in hot:scores.update(self.hot.live[j])
        if f>=0:
            needle=v(f)
            for bodykey,payload in cache.items():
                typ,j=bodykey
                if typ==EVENT and j not in hot and contains(payload,needle):
                    resident.append(j)
                    scores.update(unpack(payload))
        resident.sort()
        if not resident or resident[0]>=self.fence:self.known.add(f)
        for j in resident:cache.move_to_end((EVENT,j))
        if packet==EMPTY:cache.move_to_end(key)
        else:self.cache.put(key,EMPTY)
        scores.pop(f,None)
        return best(scores,f,tie,prior),Counter({"direct_resident":1})

MODES=("append","full_reuse","raw_reuse","hot_only","residual_only","empty_hit","resident_hit")
def reader(db,cap,m):
    if m in ("empty_hit","resident_hit"):return ResidentHit(db,cap,m=="resident_hit")
    return control_fast.reader(db,cap,m)

def main():
    p=argparse.ArgumentParser();p.add_argument("--verify",action="store_true");opts=p.parse_args()
    core.ARMS=MODES
    core.reader=reader
    raw=HERE/"hit-runs.json.gz";out=HERE/"hit-results.json"
    if opts.verify:
        r=load(raw)
        assert all(core.sha256((HERE/n).read_bytes()).hexdigest()==h for n,h in r["hashes"].items())
        assert core.measures(r["blocks"])==load(out)
        return
    ops={g+"/"+repo:prepare(s,"B")[0] for g,f in core.GROUPS.items() for repo,s in load(f).items()}
    orig=load(HERE/"runs.json.gz")["blocks"][0]
    seed=60178
    rng=Random(seed);blocks=[]
    with TemporaryDirectory(dir=HERE) as tmp:
        path=Path(tmp)/"history.sqlite"
        for rep in range(5):
            b={}
            for k in rng.sample(list(ops),len(ops)):
                case=core.run_case(path,ops[k],rng);path.unlink()
                assert case["rank_digest"]==orig[k]["rank_digest"]
                for row,ref in zip(case["queries"],orig[k]["queries"],strict=True):
                    assert row[:2]==ref[:2]
                    for cap in (1024,4096):
                        assert all(row[2][f"{cap}/{mode}"]==ref[2][f"{cap}/residual_only"] for mode in ("residual_only","empty_hit","resident_hit"))
                if blocks:
                    assert blocks[0][k]["queries"]==case["queries"]
                    del case["queries"]
                b[k]=case
            blocks.append(b);print("hit block",rep+1,flush=True)
    save(raw,{"blocks":blocks,"seed":seed,"hashes":{n:core.sha256((HERE/n).read_bytes()).hexdigest() for n in ("HIT_PROTOCOL.md","bench.py","residual.py","control_fast.py","resident_hit.py")}})
    save(out,core.measures(blocks))
if __name__=="__main__":main()

