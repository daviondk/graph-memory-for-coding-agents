"""Optional CPU scheduling helper for the last two distinct repositories."""
from source import ROOT,load_json,write_json
from embed import run
from encoder import engine
if __name__=='__main__':
    enc=engine()
    sample=load_json(ROOT/'sample.json')['selected']
    for r in reversed(sample[-2:]):
        t=r['issue'];p=ROOT/'dense'/(t+'.json')
        if p.exists():continue
        record=run(t,enc)
        assert record['corpus_sha256']==r['corpus_sha256'] and len(record['candidates'])==r['functions']
        tmp=p.with_suffix('.tail.tmp');write_json(tmp,record);tmp.replace(p)
        print(t,len(record['candidates']),round(record['timing_s'],1),flush=True)
