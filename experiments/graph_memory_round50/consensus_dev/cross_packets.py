"""Quantify packet changes when replacing Full Support checkpoint GPU orders with their CPU replay."""
from build_packets import *
import importlib.util
def main():
    original=read(D/"packets.json.gz");pool=read(D/"pool.json.gz")
    rd=Reader(False);fn=rd.lib.packet;fn.argtypes=[ct.c_int]*3+[ct.c_void_p]*4;fn.restype=ct.c_int
    inputs=read(D/"input-seal.json")["files"]
    modified={}
    rank_counts={}
    for s in SEEDS:
        a=f"ranks-{s}.json.gz";b=f"archive-{s}.json.gz";c=f"utility-{s}.f64.gz"
        assert all(sha(D/x)==inputs[x] for x in [a,b,c])
        ranks=read(D/a);prior=read(D/b);delta=read(D/f"cross-cpu-{s}.json.gz")
        e=read(D/f"native-{s}-seal.json")
        assert len(delta)==e["cpu_full_order_disagree"]
        top5=sum(ranks[q][2][:5]!=o[:5] for q,o in delta.items());assert top5==e["cpu_top5_order_disagree"]
        tv=np.frombuffer(gzip.decompress((D/c).read_bytes()),dtype="<f8");ofs=0
        for q,p in sorted(pool.items()):
            n=len(p["c"])
            if q in delta:
                o=np.asarray(delta[q],dtype=np.int32);co=np.asarray(p["c"],dtype=np.int32)
                ranks[q][2]=delta[q];prior[q][1][0]=select(fn,0,1,dict(order=o,costs=co),tv[ofs:ofs+n])
            ofs+=n
        assert ofs==len(tv)
        modified[a]=ranks;modified[b]=prior;rank_counts[s]={"order":len(delta),"top5":top5}
    target=signed_at(IMPL,"run.py")
    spec=importlib.util.spec_from_file_location("ensemble_cross",target)
    engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
    class Output:
        def __truediv__(self,name):
            if name=="PROTOCOL_RU.md":return signed_at(IMPL,name)
            return D/("cross-"+name)
    engine.D=Output()
    def getdata(name):
        assert sha(D/name)==inputs[name];return D/name
    engine.signed=getdata
    real=engine.read
    engine.read=lambda p:modified[p.name] if p.parent==D and p.name in modified else real(p)
    engine.main()
    altered=read(D/"cross-packets.json.gz");assert set(altered)==set(original)
    report={};diff={}
    for q,(t,panels) in original.items():
        tc,pp=altered[q];assert tc==t and panels[0]==pp[0]
        cases={}
        for arm,before in panels[1].items():
            after=pp[1][arm]; hit=report.setdefault(arm,dict(order=0,members=0))
            if before!=after:
                hit["order"]+=1;hit["members"]+=int(set(before)!=set(after))
                cases[arm]=[before,after]
        if cases:diff[q]=cases
    put(D/"cross-differences.json.gz",diff);put(D/"cross-summary.json",dict(ranks=rank_counts,packets=report,changed_questions=len(diff),source=sha(Path(__file__)),forecasts=sha(D/"cross-packets.json.gz")))
    print(report)
if __name__=="__main__":main()

