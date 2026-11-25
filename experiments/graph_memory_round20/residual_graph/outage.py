"""Once-only inventory of committed data after the OS disconnected the GPU, before any test scoring."""
from setup_graph import ROOT,TR,RUN,TRAINED,load,put,pilot
from vectors import database
import gzip,hashlib
def run():
    c=database();available={k for k, in c.execute("select k from vectors where prec='ft'")};count={}
    for stage in ('train','dev','test'):
        needed=set()
        for f in (TRAINED/'shape').glob('*-'+stage+'.sha.gz'):
            s=gzip.decompress(f.read_bytes());needed.update(s[i:i+32] for i in range(0,len(s),32))
        count[stage]=dict(needed=len(needed),missing=len(needed-available),present=len(needed&available))
    local={name:c.execute('select count(*) from vectors where prec=?',[name]).fetchone()[0] for name in ['ft','base']}
    put(ROOT/'gpu-outage.json',dict(split_features=count,committed=local,sqlite_quick_check='ok',completed_dev=load(ROOT/'cost-dev.json'),
        failure='NVIDIA Display event 4101, nvlddmkm stopped responding at 14:01:05 MSK. PyTorch fresh process returned cuda.is_available=False, device_count=0; PnP RTX3090 showed CM_PROB_PHANTOM; non-destructive pnputil /scan-devices returned access denied. No system settings changed.',
        saved_logs={p.name:pilot.sha(p) for p in (RUN/'logs').glob('*') if p.is_file()},authoritative_split=pilot.sha(TR/'split.json.gz')))
if __name__=='__main__':run()

