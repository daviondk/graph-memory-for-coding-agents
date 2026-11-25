"""Secondary controls formed solely from the two previously sealed forecast files."""
from collections import defaultdict,Counter
from pathlib import Path
import sys
import numpy as np
from sources import D,C,read,dump,sha
from paired_times import rg,savegz,diagnostics,compare

def predict():
    x=read(D/'followup-forecast-lock.json')
    assert sha((D/'followup-forecasts.json.gz').read_bytes())==x['forecasts']
    out=[]
    for record in rg(D/'followup-forecasts.json.gz'):
        events={ev['t']:ev['arms'] for ev in record['text']}
        for item in record['rows']:
            arms={}
            for m in ('symbol_latest','symbol_latest_operations'):
                states=[item['producer'] in events[item[k]][m] for k in ('a','b')]
                arms[m+'/query']=states
                arms[m+'/early']=states[:1]*2
                arms[m+'/late']=states[1:]*2
            for label in ('two_unique','one_early','one_late','latest_at_query'):
                arms[label]=item['arms'][label]
            qr=arms['latest_at_query']
            arms['value_last/late']=qr[1:]*2
            out.append(dict(trace=record['trace'],first=item['first'],next=item['next'],arms=arms))
    file=D/'binding-forecasts.json.gz';savegz(file,out)
    dump(D/'binding-forecast-lock.json',dict(base=x['forecasts'],code=sha(Path(__file__).read_bytes()),predictions=sha(file.read_bytes())))
def score():
    lock=read(D/'binding-forecast-lock.json');p=D/'binding-forecasts.json.gz';assert sha(p.read_bytes())==lock['predictions'] and sha(Path(__file__).read_bytes())==lock['code']
    gold={(z['trace'],z['first'],z['next']):z['truth'] for z in rg(D/'time-query-outcomes.json.gz')}
    meta={r['trace']:r for r in read(D/'corpus-audit.json')}
    bins=defaultdict(lambda:defaultdict(lambda:defaultdict(lambda:np.zeros(6,dtype=int))))
    for row in rg(p):
        truth=gold[row['trace'],row['first'],row['next']]
        fam=meta[row['trace']]['family']
        for k,pr in row['arms'].items():
            s=np.zeros(6,int);s[4]=1;s[5]=int(pr==truth)
            for x,y in zip(pr,truth):
                s[0 if x and y else 1 if x else 2 if y else 3]+=1
            bins['all'][k][fam]+=s
            if fam!='case/pplant':bins['without_pplant'][k][fam]+=s
    result={}
    for name,grp in bins.items():
        contrasts=[('two_unique','value_last/late'),('two_unique','symbol_latest/query'),('two_unique','symbol_latest_operations/query'),
                   ('symbol_latest/query','symbol_latest/early'),('symbol_latest/query','symbol_latest/late'),('symbol_latest_operations/query','symbol_latest_operations/early')]
        result[name]=dict(families=len(next(iter(grp.values()))),arms=diagnostics(grp),differences={a+' minus '+b:compare(grp,a,b) for a,b in contrasts})
        print(name,{k:(int(round(r['both_accuracy']*r['trials'])),r['trials']) for k,r in result[name]['arms'].items()})
    dump(D/'binding-results.json',result)
if __name__=='__main__':{'predict':predict,'score':score}[sys.argv[1]]()

