"""Direct complete-index and hot-only controls; run a separate randomized crossover."""
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location
from tempfile import TemporaryDirectory
from random import Random
import argparse
from residual import BARE,CapturedBodies,EXP,Fast,Hot,Residual,add,build,load,prepare,save,unpack,unpack_full,v,varints
from lazy_reader import POST
HERE=Path(__file__).resolve().parent
spec=spec_from_file_location("coverage_measurement",HERE/"bench.py")
core=module_from_spec(spec)
spec.loader.exec_module(core)
CONTROLS=("append","full_reuse","raw_reuse","delta_reuse","hot_only","residual_only")
SEED=600167

class PacketReuse(Fast):
    def admit(self,f,ids,record,stats):
        if record is not None:return record
        if self.mode=="raw_reuse":return bytes((0,))+varints(ids)
        return build(ids,self.mode=="delta_reuse")

class HotOnly(Fast):
    def __init__(self,db,hot,mode,cap):
        super().__init__(db,hot,mode,cap)
        self.hot.live=CapturedBodies()
    def resident(self,f,hot,stats):return hot
    def recover(self,record,present):
        cold=unpack(record[1:])
        return sorted((*cold,*present)),len(cold)
    def admit(self,f,ids,record,stats):
        if record is not None:return record
        hot=self.hot.incident.get(f,())
        return bytes((BARE,))+varints(j for j in ids if j not in hot)
    def after_write(self,j,fs):
        for j,body in self.hot.live.losses:
            suffix=None
            for f in body:
                key=(POST,f)
                prior=self.cache.items.get(key)
                if prior is not None:
                    if suffix is None:suffix=v(j)
                    self.cache.put(key,prior+suffix,refresh=False)
                    self.cache.updates+=1
        self.hot.live.losses.clear()

def reader(db,cap,mode):
    if mode=="hot_only":return HotOnly(db,Hot(),mode,cap)
    if mode=="residual_only":return Residual(db,cap,mode)
    if mode=="append":return Fast(db,Hot(),mode,cap)
    return PacketReuse(db,Hot(),mode,cap)

def main():
    args=argparse.ArgumentParser();args.add_argument("--verify",action="store_true");args=args.parse_args()
    core.ARMS=CONTROLS
    core.reader=reader
    raw=HERE/"control-runs.json.gz"; dest=HERE/"control-results.json"
    if args.verify:
        data=load(raw)
        for n,h in data["hashes"].items():assert core.sha256((HERE/n).read_bytes()).hexdigest()==h
        assert core.measures(data["blocks"])==load(dest)
        return
    hashes={n:core.sha256((HERE/n).read_bytes()).hexdigest() for n in ("CONTROL_PROTOCOL.md","control_fast.py","residual.py","bench.py")}
    ops={g+"/"+repo:prepare(s,"B")[0] for g,f in core.GROUPS.items() for repo,s in load(f).items()}
    orig=load(HERE/"runs.json.gz")["blocks"][0]
    rng=Random(SEED);blocks=[]
    with TemporaryDirectory(dir=HERE) as tmp:
        path=Path(tmp)/"history.sqlite"
        for rep in range(5):
            b={}
            for k in rng.sample(list(ops),len(ops)):
                case=core.run_case(path,ops[k],rng);path.unlink()
                assert case["rank_digest"]==orig[k]["rank_digest"]
                for received,old in zip(case["queries"],orig[k]["queries"],strict=True):
                    assert received[:2]==old[:2]
                    for cap in (1024,4096):
                        for m in ("residual_only","append"):
                            code=f"{cap}/{m}"
                            assert received[2][code]==old[2][code]
                if blocks:
                    assert case["queries"]==blocks[0][k]["queries"]
                    del case["queries"]
                b[k]=case
            blocks.append(b);print("control block",rep+1,flush=True)
    save(raw,{"blocks":blocks,"hashes":hashes,"seed":SEED})
    save(dest,core.measures(blocks))
if __name__=="__main__":main()

