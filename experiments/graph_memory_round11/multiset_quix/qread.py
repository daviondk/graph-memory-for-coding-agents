from qutil import Q,R9,load,put,sha
from exact import direct
import base64
def main():
    seals=load(Q/'state_seal.json')
    for p,h in seals['local'].items():
        if p.startswith('states') or p=='exact.py':assert sha(Q/p)==h
    rows=[]
    for p in sorted((Q/'states').glob('*.gz')):
        x=load(p);q=list(map(str,load(Q/'future'/p.name)['changed']))
        for b,s,m,enc,meta in x['states']:
            raw=base64.b64decode(enc);assert len(raw)==b*x['n']
            rows.append([x['task'],x['direction'],b,s,m,direct(raw,q),len(raw),meta])
    put(Q/'readouts.json.gz',rows)
    put(Q/'read_seal.json',{str(p.relative_to(Q)):sha(p) for p in [Q/'readouts.json.gz',Q/'qread.py',Q/'state_seal.json',*(Q/'future').glob('*.gz')]})
if __name__=='__main__':main()