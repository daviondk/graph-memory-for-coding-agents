"""Decode and read in a fresh process. Old graphs and rosters are never loaded."""
import base64
import statistics,time
from common import ROOT,load,put,locks,sha
from reader import read
def main():
    seal=load(ROOT/'state_seal.json')['local']
    assert all(sha(ROOT/n)==s for n,s in seal.items() if n.startswith('states/') or n in ['reader.py','common.py','query.py'])
    rows=[]
    for p in sorted((ROOT/'states').rglob('*.json.gz')):
        c=load(p);future=load(ROOT/'future'/c['panel']/p.name)['changed']
        for r in c['states']:
            data=base64.b64decode(r['data'],validate=True)
            assert len(data)==r['b']*c['n']
            times=[];out=None
            for _ in range(5):
                t=time.process_time_ns();value=read(data,future);times.append(time.process_time_ns()-t)
                assert out is None or out==value
                out=value
            rows.append([c['panel'],c['issue'],c['direction'],r['b'],r['salt'],r['arm'],value,int(statistics.median(times)),r['cpu_write_ns'],len(data),r['parameters']['used'],r['parameters']['type']])
    put(ROOT/'reads.json.gz',dict(columns=['panel','issue','direction','bytes_per_test','salt','arm','mask','read_cpu_ns','write_cpu_ns','capacity','used','representation'],rows=rows))
    put(ROOT/'read_seal.json',locks([ROOT/'reads.json.gz',ROOT/'state_seal.json',ROOT/'query.py',*(ROOT/'future').rglob('*.json.gz')]))
    print('locked readouts',len(rows))
if __name__=='__main__':main()
