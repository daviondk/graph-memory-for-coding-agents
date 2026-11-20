"""Storage-only query process. No event data, future rows or test results loaded."""
import base64
from util12 import D,load,dump,sha
from store12 import regions_read
def main():
    seal=load(D/'state_seal.json')
    for p,h in seal['local'].items():
        if p.startswith('states/') or p=='store12.py':assert sha(D/p)==h
    files={}
    for p in sorted((D/'states').glob('*.gz')):
        x=load(p);t=x['task'];probes=load(D/'probes'/p.name);qs=probes['keys'];rows=[]
        for step,phase,b,s,gate,arm,encoded,rg,reads,stats in x['rows']:
            raw=base64.b64decode(encoded,validate=True);reader=regions_read(raw)
            pred=bytes(reader(key) for key in qs)
            rows.append([step,phase,b,s,gate,arm,base64.b64encode(pred).decode()])
        out=D/'predictions'/p.name;dump(out,dict(task=t,keys=qs,rows=rows));files[out.relative_to(D).as_posix()]=sha(out)
        probe=D/'probes'/p.name;files[probe.relative_to(D).as_posix()]=sha(probe)
    files['state_seal.json']=sha(D/'state_seal.json');files['read.py']=sha(D/'read.py');dump(D/'read_seal.json',files)
if __name__=='__main__':main()